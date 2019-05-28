from __future__ import absolute_import, division

import logging
import os
import os.path as pth
from contextlib import contextmanager

import sys
import warnings

import iris
from iris.coord_systems import GeogCS
from iris.util import guess_coord_axis

import xarray as xr


"""
Mainly filter some user warning such as:
u'forecast_reference_time' referenced by variable 
u'direct_surface_sw_flux_corrected': Dimensions (u'time',) 
do not span (u'time_0', u'latitude', u'longitude')
"""
warnings.filterwarnings("ignore", category=UserWarning)

cs = GeogCS(6371229)


@contextmanager
def inprogress_fname(fname):
    """
    Yield a temporary filename that can be used for writing to.
    Once the context is complete, the temporary file will be moved
    to the desired destination. Great for having an "in progress"
    type operation where we don't want the file to be put in the final
    location until it is complete.

    """
    name, ext = pth.splitext(pth.basename(fname))
    tmp_fname = pth.join(pth.dirname(fname),
                         '_{}{}.inprogress'.format(name, ext))
    if pth.exists(fname):
        raise IOError('{} already exists. Remove it first'.format(fname))
    if pth.exists(tmp_fname):
        raise IOError('{} already exists. Remove it first'.format(tmp_fname))

    try:
        yield tmp_fname
        os.rename(tmp_fname, fname)
    finally:
        # No matter what happens, remove the temporary file (it *has*
        # been created during the lifetime of this context).
        if pth.exists(tmp_fname):
            os.remove(tmp_fname)


def callback(cube, field, fname):
    # Some cubes didn't even have a time coord! (PDT 4.5)
    if not cube.coords('forecast_reference_time') and cube.coords('time') \
            and cube.coords('forecast_period'):
        t = cube.coord('time')
        fp = cube.coord('forecast_period')
        frt = iris.coords.DimCoord(
            t.points - fp.points,
            standard_name='forecast_reference_time', units=t.units)
        cube.add_aux_coord(frt)

    # The special attribute does exist, then add aux_coord & attribute to the
    # metadata. TODO: need to check whether this is always necessary for
    # pressure data.
    if getattr(field, 'scaledValueOfFirstFixedSurface', None) is not None:
        scaledValueOfFirstFixedSurface = field.scaledValueOfFirstFixedSurface
        scaledValueOfSecondFixedSurface = field.scaledValueOfSecondFixedSurface
        vert = iris.coords.DimCoord(long_name='scaled_Value_Of_Fixed_Surface',
                                    points=[scaledValueOfFirstFixedSurface],
                                    bounds=[scaledValueOfFirstFixedSurface,
                                            scaledValueOfSecondFixedSurface])
        cube.add_aux_coord(vert)

        cube.attributes['GribParam'] = (field.discipline,
                                        field.parameterCategory,
                                        field.parameterNumber,
                                        field.typeOfFirstFixedSurface,
                                        field.typeOfSecondFixedSurface)


def main():
    import argparse

    # screen output timestamp, which can be piped into supervisord logfile
    logging.basicConfig(stream=sys.stdout, level=logging.INFO,
                        format='%(asctime)s %(message)s')

    parser = argparse.ArgumentParser(description='Process um files and save \
                                                  into NetCDF.')
    parser.add_argument('--input', required=True, nargs='+',
                        help='the input filename')
    parser.add_argument('--output', required=True,
                        help='the filename to create')
    parser.add_argument('--nc_type', default='NETCDF4', help="convert NetCDF \
                        format, ie. 'NETCDF3_CLASSIC' OR 'NETCDF4'. ")
    args = parser.parse_args()
    transform(args.input, args.output, args.nc_type)


class Transformer(object):
    def __init__(self):
        self._cubes = iris.cube.CubeList([])

    def __getstate__(self):
        return self.__getstate__

    # @threaded
    def load(self, fname):
        # Use callback for cf name convention
        cubes = iris.load(fname, callback=callback)

        # Make sure the cubes are not single variable by filtering
        # TODO: catch UserWarnings to do this
        for cube in cubes:
            if cube.coords('latitude') and cube.coords('longitude'):
                self._cubes.append(cube)

        # Make sure the coord_system exits for each dimension in cube
        # Otherwise the save will fail
        for cube in self._cubes:
            # Using 'dim_coords=True' to differentiate dim_coord (ie. time)
            # with aux_coord, i.e. forecast_period
            for coord in cube.coords(dim_coords=True):
                if not coord.coord_system:
                    coord.coord_system = cs

    def transform(self):
        # Modify the attribute 'positive' so the 'guess' function
        # won't recognize the 'soil_level' as axis Z
        for cube in self._cubes:
            if cube.coords('soil_model_level_number'):
                coord = cube.coord('soil_model_level_number')
                if coord.attributes:
                    coord.attributes.pop('positive')
                    guess_coord_axis(coord)

            # This handles the depth below land surface
            if cube.coords('depth'):
                coord = cube.coord('depth')
                if coord.attributes:
                    coord.attributes.pop('positive')
                    guess_coord_axis(coord)

            # Make cfdata be consitent with iris CF_GRIB2_TABLE
            if 'type_cloud_area_fraction' in cube.name():
                cube.units = '%'
            if cube.name() == 'soil_moisture_content':
                cube.units = 'kg m-2'
            if cube.name() == 'canopy_water_amount':
                cube.units = 'kg m-2'


    def save(self, fname, nc_type, compress=True, complevel=4):
        # Future versions of Iris change their defaults. We enable the new
        # defaults here to simplify future compatibility.
        # iris.FUTURE.netcdf_no_unlimited = True

        basedir = os.path.abspath(os.path.dirname(fname))
        if not os.path.isdir(basedir):
            os.makedirs(basedir)

        if not self._cubes:
            # Touch the file
            with open(fname, 'a'):
                os.utime(fname, None)
        else:
            output_fpath = fname
            print("Saving the NetCDF file now ...")
            with inprogress_fname(output_fpath) as tmp_fname:
                # NETCDF4 with zlib to compress
                if nc_type == 'NETCDF4':
                    iris.save(self._cubes, tmp_fname,
                              saver=iris.fileformats.netcdf.save,
                              netcdf_format=nc_type,
                              zlib=compress, complevel=complevel)
                elif nc_type == 'NETCDF3_CLASSIC':
                    # Note: no compression is avail for nc3
                    iris.save(self._cubes, tmp_fname,
                              saver=iris.fileformats.netcdf.save,
                              netcdf_format=nc_type)
                else:
                    raise ValueError(
                        'Not the available nc_type to convert!')
            logging.info(output_fpath + ' is saved')

    def save_xarray(self, fname, engine='netcdf4', encoding=dict(zlib=True, complevel=4)):
        # Future versions of Iris change their defaults. We enable the new
        # defaults here to simplify future compatibility.
        # iris.FUTURE.netcdf_no_unlimited = True

        basedir = os.path.abspath(os.path.dirname(fname))
        if not os.path.isdir(basedir):
            os.makedirs(basedir)

        if not self._cubes:
            # Touch the file
            with open(fname, 'a'):
                os.utime(fname, None)
        else:
            output_fpath = fname
            print("Saving the NetCDF file now ...")
            with inprogress_fname(output_fpath) as tmp_fname:
                vars = []
                for cube in self._cubes:
                    try:
                        vars.append(xr.DataArray.from_iris(cube))
                    except Error as e:
                        print(e)
                        print('Failed to convert ')
                        print(cube)
                ds = xr.merge(vars)
                # ds = xr.concat([xr.DataArray.from_iris(cube) for cube in self._cubes])
                print(ds)
                ds.to_netcdf(tmp_fname, engine=engine, encoding={var: encoding for var in ds.data_vars})
            logging.info(output_fpath + ' is saved')


def transform(input_fpath, output_fpath, nc_type):
    t = Transformer()
    t.load(input_fpath)
    t.transform()
    # t.save(output_fpath, nc_type)
    # t.save(output_fpath, nc_type, compress=False, complevel=0)
    t.save(output_fpath, nc_type, complevel=1)
    # t.save_xarray(output_fpath, encoding={})
    # t.save_xarray(output_fpath, encoding={'zlib':True, 'complevel':1})
    # t.save_xarray(output_fpath, engine='h5netcdf', encoding={})
    # t.save_xarray(output_fpath, engine='h5netcdf', encoding={'zlib':True, 'complevel':1})

if __name__ == '__main__':
    main()
