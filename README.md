# Speed_up_Iris_NetCDF_Saving
Code to optimise and speed-up the process of using Iris to save NetCDF files.


## Create a workable Python Env with Iris2.2.

```bash
conda create -n iris2-py2 python=2 iris -c conda-forge --quiet --yes

source activate iris2-py2

```

## How to Run
After cloning the repository, one can run the bash script directly by modifying the testing input file.
```
$ ./test_nc_converter.sh
```

## View the cProfile
The cProfile is output at ./nc_covert/docs/converter.cprofile




