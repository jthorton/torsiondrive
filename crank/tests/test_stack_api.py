"""
Unit and regression test for the crank package.
"""

import os, sys, collections, pytest
import numpy as np
from crank.crankAPI import crank_api
import geometric
from geometric.nifty import ang2bohr
from crank import crankServerAPI

try:
    import qcengine
    import psi4
except:
    pass

class SimpleServer:
    """ A simple server that interfaces with crank and geometric to do the dihedral scanning work flow """
    def __init__(self, xyzfilename, dihedrals, grid_spacing):
        self.M = geometric.molecule.Molecule(xyzfilename)
        self.dihedrals = dihedrals
        self.grid_spacing = grid_spacing
        self.elements = self.M.elem
        self.init_coords = [(self.M.xyzs[0] * ang2bohr).ravel().tolist()]

    def run_crank_scan(self):
        """
        Run crank scan in the following steps:
        1. Create json input for crank
        2. Send the json input dictionary to crankAPI.crank_api(), get the next set of jobs
        3. If there are no jobs needed, finish and return the lowest energy on each dihedral grid
        4. If there are new jobs, run them with geomeTRIC.run_json.
        5. Collect the results and put them into new json input dictionary
        6. Go back to step 2.
        """
        # step 1
        crank_state = crankServerAPI.create_initial_api_input(dihedrals=self.dihedrals, grid_spacing=self.grid_spacing, elements=self.elements, init_coords=self.init_coords)
        while True:
            # step 2
            next_jobs = crank_api(crank_state, verbose=True)
            # step 3
            if len(next_jobs) == 0:
                print("Crank Scan Finished")
                return crankServerAPI.collect_lowest_energies(crank_state)
            # step 4
            job_results = collections.defaultdict(list)
            for grid_id_str, job_geo_list in next_jobs.items():
                for job_geo in job_geo_list:
                    dihedral_values = tuple(int(i) for i in grid_id_str.split(','))
                    geometric_input_dict = self.make_geomeTRIC_input(dihedral_values, job_geo)
                    geometric_output_dict = geometric.run_json.geometric_run_json(geometric_input_dict)
                    final_geo = geometric_output_dict['final_molecule']['molecule']['geometry']
                    final_energy = geometric_output_dict['final_molecule']['properties']['return_energy']
                    # Note: the results should be appended in the same order as in the inputs
                    # It's not a problem here when running serial for loop
                    job_results[grid_id_str].append((job_geo, final_geo, final_energy))
            # step 5
            crank_state = crankServerAPI.update_crank_state(crank_state, job_results)
            # step 6


    def make_geomeTRIC_input(self, dihedral_values, geometry):
        """ This function should be implemented on the server, that takes QM specs, geometry and constraint
        to generate a geomeTRIC json input dictionary"""
        constraints_string = "$set\n"
        for (d1, d2, d3, d4), v in zip(self.dihedrals, dihedral_values):
            # geomeTRIC use atomic index starting from 1
            constraints_string += "dihedral %d %d %d %d %f\n" % (d1+1, d2+1, d3+1, d4+1, v)
        qc_schema_input = {
            "schema_name": "qc_schema_input",
            "schema_version": 1,
            "molecule": {
                "geometry": geometry,
                "symbols": self.M.elem
            },
            "driver": "gradient",
            "model": {
                "method": "MP2",
                "basis": "cc-pvdz"
            },
            "keywords": {}
        }
        geometric_input_dict = {
            "schema_name": "qc_schema_optimization_input",
            "schema_version": 1,
            "keywords": {
                "coordsys": "tric",
                'constraints': constraints_string,
                "program": "psi4"
            },
            "input_specification": qc_schema_input
        }
        return geometric_input_dict


@pytest.mark.skipif("qcengine" not in sys.modules, reason='qcengine not found')
@pytest.mark.skipif("psi4" not in sys.modules, reason='psi4 not found')
def test_stack_simpleserver():
    """
    Test the stack of crank -> geomeTRIC -> qcengine -> Psi4
    """
    orig_path = os.getcwd()
    this_file_folder = os.path.dirname(os.path.realpath(__file__))
    test_folder = os.path.join(this_file_folder, 'files', 'hooh-simpleserver')
    os.chdir(test_folder)
    simpleServer = SimpleServer('start.xyz', dihedrals=[[0,1,2,3]], grid_spacing=[30])
    lowest_energies = simpleServer.run_crank_scan()
    result_energies = [lowest_energies[grid_id] for grid_id in sorted(lowest_energies.keys())]
    assert np.allclose(result_energies, [-151.17383,-151.17416,-151.17455,-151.17477,-151.17455,-151.17367,-151.17199,
        -151.16962,-151.16686,-151.16424,-151.16236,-151.16167,-151.16236,-151.16424,-151.16686,-151.16962,-151.17199,
        -151.17367,-151.17455,-151.17477,-151.17455,-151.17416,-151.17383,-151.17370][1::2], atol=1e-4)
    os.chdir(orig_path)