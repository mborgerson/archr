#!/bin/bash
set -e
# set -x

URL=http://www.downloads.netgear.com/files/GDC/WNAP320/WNAP320%20Firmware%20Version%202.0.3.zip
FILE="WNAP320 Firmware Version 2.0.3.zip"
NAME="wnap320"

# Download firmware image:
if [ ! -e "$FILE" ]; then
	echo "[**] Downloading $FILE..."
	wget $URL
fi

# Initial firmadyne image:
if [ ! -d firmadyne ]; then
	echo "[**] Cloning Firmadyne..."
	git clone --recurse-submodules https://github.com/firmadyne/firmadyne.git
fi

echo "[**] Building Firmadyne Image"
pushd firmadyne
docker build -t firmadyne .
popd

# Initial build of container image:
echo "[**] Building FW Container Image"
docker build -t ${NAME} --build-arg FW_FILE="$FILE" .

# Initial firmadyne analysis:
docker run --privileged -it --net=host --name=${NAME}_container ${NAME}

echo "[**] Initial analysis complete"

# Create image based on initial analysis:
docker commit --change "cmd [\"/firmadyne/run.sh\"]" ${NAME}_container ${NAME}:post-analysis
docker rm ${NAME}_container

# Finally, run firmware:
echo "[**] Done"
echo "Run with: docker run --privileged -it --net=host --rm --name=${NAME}_container ${NAME}:post-analysis"
