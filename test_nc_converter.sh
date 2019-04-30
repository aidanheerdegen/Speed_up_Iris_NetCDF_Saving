#!/bin/bash

#set -x

# start time
date
start_time=`date +%s`

NC_CONVERTER_DIR=${PWD}/nc_convert
cd ${NC_CONVERTER_DIR}

# change this to your local work directory
# samples are sitting there
LOCAL_WORK_DIR=${NC_CONVERTER_DIR}/tests

# sample UM file name
sample_input=qwxbjva_pf003_2016120100_utc_fc.um


#  Passed test reformat slv file (now working for slv)
python -m cProfile -o ${NC_CONVERTER_DIR}/docs/converter.cprof ${NC_CONVERTER_DIR}/convert_um_to_nc.py \
--input ${LOCAL_WORK_DIR}/$sample_input \
--output ${LOCAL_WORK_DIR}/$sample_input.test01.nc

date
end=`date +%s`
runtime=$((end-start_time))

echo start time: $start_time
echo end time: $end

echo Run time: $runtime seconds

