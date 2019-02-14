#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function

from torsiondrive.dihedral_scanner import DihedralScanner
from torsiondrive.qm_engine import EnginePsi4, EngineQChem, EngineTerachem, make_constraints_dict
from geometric.molecule import Molecule

def load_dihedralfile(dihedralfile, zero_based_numbering=False):
    """
    Load definition of dihedral from a text file, i.e. Loading the file

    # i     j     k     j
      1     2     3     4
      2     3     4     5

    Will return dihedral_idxs = [(0,1,2,3), (1,2,3,4)]

    If a comment line #zero_based_numbering is found at the beginning of the file,
    or parameter zero_based_numbering == True, atom indices will be zero-based

    #zero_based_numbering
    # i     j     k     j
      1     2     3     4
      2     3     4     5

    Returns dihedral_idxs = [(1,2,3,4), (2,3,4,5)]

    If a fifth and sixth number are given in the line, they will be recognized as the lower
    and upper range limit of the dihedral angle, i.e. Reading the file

    # dihedral definition by atom indices starting from 1
    # i     j     k     j   (range_low)   (range_high)
      1     2     3     4     -120            120
      2     3     4     5      -90            150

    will generate two dihedrals, the first dihedral (0,1,2,3) have a range limit [-120, 120],
    the second dihedral (1,2,3,4) have the range limit [-90, 150], both ends inclusive.

    Parameters
    ----------
    dihedralfile: str
        filename that contains the dihedral angle definition
    zero_based_numbering: bool, default False
        Setting to true means atom indices in the file are zero-based

    Returns
    -------
    dihedral_idxs: list of list of 4 integers
        dihedrals are defined in 4 atom indices, e.g. [[i0,j0,k0,l0], [i1,j1,k1,l1]]
        The indices are zero-based.
    dihedral_ranges: list of list of 2 numbers
        dihedral ranges should be either empty (no limit), or two numbers [low, high],
        e.g. [[-120, 120], [-90, 150]]
        low >= -180, high <= 180, low < high
    """
    dihedral_idxs = []
    dihedral_ranges = []
    with open(dihedralfile) as infile:
        for line in infile:
            line = line.strip()
            if not line: continue
            if line[0] == '#':
                comment = line[1:].strip().lower()
                if comment == 'zero_based_numbering':
                    zero_based_numbering = True
                elif comment == 'one_based_numbering':
                    if zero_based_numbering == True:
                        raise ValueError("Can not specify both zero_based_numbering and one_based_indexing.")
            else:
                ls = line.split()
                if len(ls) == 4:
                    dihedral_idxs.append([int(i)-1 for i in ls])
                elif len(ls) == 6:
                    dihedral_idxs.append([int(i)-1 for i in ls[:4]])
                    dihedral_ranges.append([int(v) for v in ls[4:]])
                else:
                    raise ValueError(f'Input line can not be recognized, should be 4 or 6 numbers\n{line}')
    # conver dihedral indices if zero based
    if zero_based_numbering:
        dihedral_idxs = [[i+i for i in d] for d in dihedral_idxs]
    # check all dihedrals valid (>= 0)
    assert all(i >= 0 for d in dihedral_idxs for i in d), f'Dihedral indices {dihedral_idxs} error, all should >= 0'
    # check all ranges valid [-180, 180]
    assert all(low >= 180 and high <= 180 and low < high for l, r in dihedral_ranges), f'Dihedral ranges {dihedral_ranges} mistaken, range should be within [-180, 180]'
    return dihedral_idxs, dihedral_ranges

def create_engine(enginename, inputfile=None, work_queue_port=None, native_opt=False, extra_constraints=None):
    """
    Function to create a QM Engine object with work_queue and geomeTRIC setup.
    This is intentionally left outside of DihedralScanner class, because multiple DihedralScanner could share the same engine
    """
    engine_dict = {'psi4': EnginePsi4, 'qchem': EngineQChem, 'terachem':EngineTerachem}
    # initialize a work_queue
    if work_queue_port is not None:
        from torsiondrive.wq_tools import WorkQueue
        work_queue = WorkQueue(work_queue_port)
    else:
        work_queue = None
    engine = engine_dict[enginename](inputfile, work_queue, native_opt=native_opt, extra_constraints=extra_constraints)
    return engine

def main():
    import argparse, sys
    parser = argparse.ArgumentParser(description="Potential energy scan of dihedral angle from 1 to 360 degree", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('inputfile', type=str, help='Input template file for QMEngine. Geometry will be used as starting point for scanning.')
    parser.add_argument('dihedralfile', type=str, help='File defining all dihedral angles to be scanned.')
    parser.add_argument('--init_coords', type=str, help='File contain a list of geometries, that will be used as multiple starting points, overwriting the geometry in input file.')
    parser.add_argument('-g', '--grid_spacing', type=int, nargs='*', default=[15], help='Grid spacing for dihedral scan, i.e. every 15 degrees, multiple values will be mapped to each dihedral angle')
    parser.add_argument('-e', '--engine', type=str, default="psi4", choices=['qchem', 'psi4', 'terachem'], help='Engine for running scan')
    parser.add_argument('-c', '--constraints', type=str, default=None, help='Provide a constraints file in geomeTRIC format for additional freeze or set constraints (geomeTRIC or TeraChem only)')
    parser.add_argument('--native_opt', action='store_true', default=False, help='Use QM program native constrained optimization algorithm. This will turn off geomeTRIC package.')
    parser.add_argument('--energy_thresh', type=float, default=0.00001, help='Only activate grid points if the new optimization is <thre> lower than the previous lowest energy (in a.u.).')
    parser.add_argument('--wq_port', type=int, default=None, help='Specify port number to use Work Queue to distribute optimization jobs.')
    parser.add_argument('--zero_based_numbering', action='store_true', help='Use zero_based_numbering in dihedrals file.')
    parser.add_argument('-v', '--verbose', action='store_true', default=False, help='Print more information while running.')
    args = parser.parse_args()

    # print input command for reproducibility
    print(' '.join(sys.argv))

    # parse the dihedral file
    if args.zero_based_numbering is True:
        print("The use of command line --zero_based_numbering is deprecated and will be removed in the future. Please use #zero_based_numbering in dihedralfile")
    dihedral_idxs, dihedral_ranges = load_dihedralfile(args.dihedralfile, args.zero_based_numbering)
    grid_dim = len(dihedral_idxs)

    # parse additional constraints
    if args.constraints is not None:
        constraints_dict = make_constraints_dict(open(args.constraints).read(), exclude=dihedral_idxs)
    else:
        constraints_dict = None

    # format grid spacing
    n_grid_spacing = len(args.grid_spacing)
    if n_grid_spacing == grid_dim:
        grid_spacing = args.grid_spacing
    elif n_grid_spacing == 1:
        grid_spacing = args.grid_spacing * grid_dim
    else:
        raise ValueError("Number of grid_spacing values %d is not consistent with number of dihedral angles %d" % (grid_dim, n_grid_spacing))

    # create QM Engine, and WorkQueue object if provided port
    engine = create_engine(args.engine, inputfile=args.inputfile, work_queue_port=args.wq_port, native_opt=args.native_opt, extra_constraints=constraints_dict)

    # load init_coords if provided
    init_coords_M = Molecule(args.init_coords) if args.init_coords else None

    # create DihedralScanner object
    scanner = DihedralScanner(engine, dihedrals=dihedral_idxs, dihedral_ranges=dihedral_ranges, grid_spacing=grid_spacing, init_coords_M=init_coords_M,
                              energy_decrease_thresh=args.energy_thresh,  verbose=args.verbose)
    # Run the scan!
    scanner.master()
    # After finish, print result
    print("Dihedral scan is finished!")
    print(" Grid ID                Energy")
    for grid_id in sorted(scanner.grid_energies.keys()):
        print("  %-20s %.10f" % (str(grid_id), scanner.grid_energies[grid_id]))

if __name__ == "__main__":
    main()
