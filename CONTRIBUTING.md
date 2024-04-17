# Getting Started
## Get the repo
Fork and clone the repo.
```
git clone --recursive https://github.com/<your-fork>/substrait-python.git
cd substrait-python
```

## Conda env
Create a conda environment with developer dependencies.
```
conda env create -f environment.yml
conda activate substrait-python-env
```

## Update the substrait submodule locally
This might be necessary if you are updating an existing checkout.
```
git submodule sync --recursive
git submodule update --init --recursive
```


# Upgrade the substrait protocol definition

## a) Use the upgrade script

Run the upgrade script to upgrade the submodule and regenerate the protobuf stubs.

```
./update_proto.sh <version>
```

## b) Manual upgrade

### Upgrade the Substrait submodule

```
cd third_party/substrait
git checkout <version>
cd -
git commit . -m "Use submodule <version>"
```

### Generate protocol buffers
Generate the protobuf files manually. Requires protobuf `v3.20.1`.
```
./gen_proto.sh
```


# Build
## Python package
Editable installation.
```
pip install -e .
```

# Test
Run tests in the project's root dir.
```
pytest
```
