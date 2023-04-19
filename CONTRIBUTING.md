
# Getting Started
## Get the repo
Fork and clone the repo.
```
git clone --recursive https://github.com/<your-fork>/substrait-python.git
cd substrait-python
```
## Update the substrait submodule locally
If you are updating an existing checkout.
```
git submodule sync --recursive
git submodule update --init --recursive
```
## Upgrade the substrait submodule
You will need to regenerate protobuf classes afterwards (`gen_proto.sh`).
```
cd third_party/substrait
git checkout <version>
cd -
git commit . -m "Use submodule <version>"
```


# Setting up your environment
## Conda env
Create a conda environment with developer dependencies.
```
conda env create -f environment.yml
conda activate pysubstrait
```

# Build
## Python package
Editable installation.
```
pip install -e .
```

## Generate protocol buffers
Generate the protobuf files manually. Requires protobuf `v3.20.1`.
```
./gen_proto.sh
```

# Test
Run tests in the project's root dir.
```
pytest
```
