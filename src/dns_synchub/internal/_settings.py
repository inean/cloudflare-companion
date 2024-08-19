from typing import Any, Mapping, get_origin

from pydantic._internal._utils import lenient_issubclass
from pydantic.fields import FieldInfo
from pydantic_settings import EnvSettingsSource
from pydantic_settings.sources import EnvNoneType
from pydantic_settings_file_envar import FileSuffixEnvSettingsSource


class _EnvSettingsSource(EnvSettingsSource):
    # This method
    def explode_env_vars(
        self, field_name: str, field: FieldInfo, env_vars: Mapping[str, str | None]
    ) -> dict[str, Any]:
        """
        Process env_vars and extract the values of keys containing env_nested_delimiter into nested dictionaries.

        This is applied to a single field, hence filtering by env_var prefix.

        Args:
            field_name: The field name.
            field: The field.
            env_vars: Environment variables.

        Returns:
            A dictionary contains extracted values from nested env values.
        """
        is_dict = lenient_issubclass(get_origin(field.annotation), dict)
        is_list = lenient_issubclass(get_origin(field.annotation), list)

        prefixes = [
            f"{env_name}{self.env_nested_delimiter}"
            for _, env_name, _ in self._extract_field_info(field, field_name)
        ]
        result: dict[str, Any] = {}
        for env_name, env_val in env_vars.items():
            if not any(env_name.startswith(prefix) for prefix in prefixes):
                continue
            # we remove the prefix before splitting in case the prefix has characters in common with the delimiter
            env_name_without_prefix = env_name[self.env_prefix_len :]
            _, *keys, last_key = env_name_without_prefix.split(self.env_nested_delimiter)
            env_var = result
            target_field: FieldInfo | None = field
            for key in keys:
                target_field = self.next_field(target_field, key, self.case_sensitive)
                if isinstance(env_var, dict):
                    env_var = env_var.setdefault(key, {})

            # get proper field with last_key
            target_field = self.next_field(target_field, last_key, self.case_sensitive)

            # check if env_val maps to a complex field and if so, parse the env_val
            if (target_field or is_dict or is_list) and env_val:
                if target_field:
                    is_complex, allow_json_failure = self._field_is_complex(target_field)
                else:
                    # nested field type is dict or list
                    is_complex, allow_json_failure = True, True
                if is_complex:
                    try:
                        env_val = self.decode_complex_value(last_key, target_field, env_val)  # type: ignore
                    except ValueError as e:
                        if not allow_json_failure:
                            raise e
            if isinstance(env_var, dict):
                if (
                    last_key not in env_var
                    or not isinstance(env_val, EnvNoneType)
                    or env_var[last_key] == {}
                ):
                    env_var[last_key] = env_val
        if is_list:
            # if field is list based, ensure keys are sequential and return an ordered list
            result, values = [], result
            for i in (str(i) for i in range(len(values))):
                if i not in values:
                    raise ValueError(f"Expected entry with index {i} for {field_name}")
                result.append(values[i])
        return result

    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[Any, str, bool]:
        # Attenpt to get field wirth default method
        env_val, fkey, is_complex = self._e_get_field_value_(field, field_name)
        # Fallback ro _FILE based get_field_value if previous method fails
        if env_val is None:
            env_val, fkey, is_complex = self._f_get_field_value_(field, field_name)
        # Return the value, key and if the value is complex
        return env_val, fkey, is_complex


EnvSettingsSource._e_get_field_value_ = EnvSettingsSource.get_field_value
EnvSettingsSource._f_get_field_value_ = FileSuffixEnvSettingsSource.get_field_value
