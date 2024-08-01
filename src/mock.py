import os

import docker
import docker.errors
import dotenv

# Load env variables
dotenv.load_dotenv()


class MockContainerCollection:
    def __init__(self, *, attrs):
        self.attrs = attrs


class MockContainers:
    def list(self):
        return []

    def get(self, container_id):
        if container_id == "0":
            raise docker.errors.NotFound("No more events")

        return MockContainerCollection(
            attrs={
                "Id": container_id,
                "Config": {
                    "Labels": {
                        os.getenv("TRAEFIK_FILTER_LABEL"): os.getenv("TRAEFIK_FILTER"),
                        "traefik.http.routers.example.rule": "Host(`example1.domain.tld`) || Host(`example2.domain.tld`)",
                    }
                },
            }
        )


class MockDockerClient:
    @property
    def containers(self):
        return MockContainers()

    def events(self, **kwargs):
        yield {"status": "start", "id": "1234"}
        yield {"status": "start", "id": "0"}


def mock_docker_from_env():
    return MockDockerClient()


docker.from_env = mock_docker_from_env


if __name__ == "__main__":
    import importlib
    import os
    import sys

    if len(sys.argv) < 2:
        print("Usage: python mock.py <module_name> [args...]")
        sys.exit(1)

    # Fetch module name and arguments
    module_name, sys.argv = sys.argv[1], sys.argv[1:]

    try:
        # Convert module name to file path
        module_file_path = os.path.join(os.getcwd(), module_name)
        loader = importlib.machinery.SourceFileLoader(module_name, module_file_path)
        # Exdecute code
        module = loader.load_module()
    except ImportError as e:
        print(e)
