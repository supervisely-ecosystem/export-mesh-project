# TEMPORARY test image: latest hardened base + the unreleased mesh SDK branch.
# Once the mesh changes are released, drop this image and point config.json's
# docker_image back at a released supervisely/import-export tag.
FROM supervisely/base-py-sdk-hardened:6.73.580

# The hardened base image has no git, so install the pinned SDK commit from the
# GitHub source tarball (no git clone needed) instead of git+https.
RUN python3 -m pip install --no-cache-dir --force-reinstall --no-deps \
    "https://github.com/supervisely/supervisely/archive/ffbd303962b17f986aeda7503ebff7169459a1fd.tar.gz"

RUN python3 -m pip install --no-cache-dir "trimesh>=3.11.2,<=4.5.0"
