#!/bin/bash
set -e
set -x

pushd /firmadyne/firmadyne
echo "ANALYZING $FW_FILE"

echo "Booting..."
./scratch/1/run.sh
