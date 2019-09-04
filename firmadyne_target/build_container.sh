#!/bin/bash
set -e
# set -x

# URL=http://www.downloads.netgear.com/files/GDC/WNDR3400V3/WNDR3400v3-V1.0.1.18_1.0.63.zip
# FILE="WNDR3400v3-V1.0.1.18_1.0.63.zip"
# NAME="wndr3400v3"

# URL=http://www.downloads.netgear.com/files/GDC/WNR2000v3/WNR2000v3_V1.1.2.12.zip
# FILE="WNR2000v3_V1.1.2.12.zip"
# NAME="wnr2000v3"

# URL=http://www.downloads.netgear.com/files/GDC/WNR2000V4/WNR2000v4-V1.0.0.64.zip
# FILE="WNR2000v4-V1.0.0.64.zip"
# NAME="wnr2000v4"

# URL=http://www.downloads.netgear.com/files/GDC/WNR2000V5/WNR2000v5-V1.0.0.34.zip
# FILE="WNR2000v5-V1.0.0.34.zip"
# NAME="wnr2000v5"

#
# Encrypted...?
#
# URL=ftp://ftp2.dlink.com/PRODUCTS/DIR-878/REVA/DIR-878_REVA_FIRMWARE_v1.12B01.zip
# FILE="DIR-878_REVA_FIRMWARE_v1.12B01.zip"
# NAME="dir-878"


# https://dlinkmea.com/index.php/product/details/?det=NmFNY0ZsYnAvN3BYZlA0a0d2blliQT09
URL=https://dlinkmea.com/upload/downloadable/7636-DSL-2740U_V1_FW_ME_1.02_webupload.rar
FILE="DSL-2740U V1 FW ME_1.02_webupload.zip"
NAME="dsl-2740u"

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
