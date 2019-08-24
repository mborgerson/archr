#!/bin/bash
set -e
set -x

pushd /firmadyne/firmadyne
echo "ANALYZING $FW_FILE"

python3 ./sources/extractor/extractor.py -b Netgear -sql 127.0.0.1 -np -nk "$FW_FILE" images

./scripts/getArch.sh ./images/1.tar.gz
./scripts/tar2db.py -i 1 -f ./images/1.tar.gz

# FIXME: Why does the following command return error status?
set +e
echo "firmadyne" | sudo -SE ./scripts/makeImage.sh 1
set -e

echo "Detecting network configuration"
./scripts/inferNetwork.sh 1

#echo "Booting..."
#./scratch/1/run.sh
