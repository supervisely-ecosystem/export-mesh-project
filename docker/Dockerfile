# TEMPORARY test image: latest hardened base + the unreleased mesh SDK branch.
# Once the mesh changes are released, drop this image and point config.json's
# docker_image back at a released supervisely/import-export tag.
FROM supervisely/base-py-sdk-hardened:6.73.580

RUN python3 -m pip install --no-cache-dir --force-reinstall --no-deps \
    "supervisely @ git+https://github.com/supervisely/supervisely.git@ffbd303962b17f986aeda7503ebff7169459a1fd"

RUN python3 -m pip install --no-cache-dir "trimesh>=3.11.2,<=4.5.0"
