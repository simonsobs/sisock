# Running Tests
We use pytest as our testing framework. To run the tests run from the top level
directory:

```
$ python3 -m pytest -p no:wampy --cov sisock tests/
```

## Plugins
We use some pytest plugins, including pytest-docker-compose. This spins
containers required for testing. As a result, you'll need docker and
docker-compose installed.
