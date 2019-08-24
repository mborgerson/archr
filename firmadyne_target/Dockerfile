from firmadyne
arg FW_FILE
env FW_FILE=${FW_FILE}
copy ["${FW_FILE}", "/firmadyne/firmadyne/"]
copy ["analysis.sh", "/firmadyne/"]
copy ["run.sh", "/firmadyne/"]
cmd ["/firmadyne/analysis.sh"]
