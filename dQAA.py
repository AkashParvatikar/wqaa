import numpy
import numpy as np
from numpy import *
import math
import scipy.stats
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from MDAnalysis.core.Timeseries import *
from MDAnalysis import *
import MDAnalysis
from jade import *
import argparse
import warnings
import timing

#a is mem-mapped array, b is array in RAM we are adding to a.
def mmap_concat(shape,b,filename):
	assert(shape[1] == b.shape[1] and shape[2] == b.shape[2]);
	c = np.memmap(filename, dtype='float64', mode='r+', shape=(shape[0]+b.shape[0],shape[1],shape[2]))
	c[shape[0]:, :, : ] = b
	newshape = c.shape;	
	del c;	#	Flushes changes to memory and then deletes.  New array can just be called using filename
	return newshape;

def phisel(res):
#MDAnalysis' phi_selection requires a segid be present while this doesn't.
	return res.universe.selectAtoms('resid %d and name C' %(res.id-1) ) + res.N + res.CA + res.C

def psisel(res):
#MDAnalysis' phi_selection requires a segid be present while this doesn't. 
	return res.N + res.CA + res.C + res.universe.selectAtoms('resid %d and name N' %(res.id+1) )

def qaa(config, val):
	num_traj = config['numOfTraj'];
	ica_dim = config['icadim'];
	start_traj = config['startTraj'];
	for i in range(start_traj,num_traj+start_traj):
		#	!Edit to your trajectory format!
		try:
			u = MDAnalysis.Universe("pentapeptide/init-ww-penta.pdb", "pentapeptide/job%i-protein.dcd" %(i+1), permissive=False);
		except:
			raise ImportError('You must edit \'dQAA.py\' to fit your trajectory format!');
			exit();
	
		atom = u.selectAtoms('backbone');
	
		phidat = TimeseriesCollection()
		psidat = TimeseriesCollection()

		#	Adds each (wanted) residues phi/psi angles to their respective timeseries collections
		if val.verbose: timing.log('Processing Trajectory %i' %(i+1));
		numres = config['numRes']
		trajlen = len(u.trajectory)
	
		#	Tailor generateConfig.py for correct for-loop iterations
		for res in range(1+config['startRes'], config['startRes']+numres-1):
			#	selection of the atoms involved for the phi angle
			phi_sel = phisel(u.residues[res])
			#	selection of the atoms involved for the psi angle
			psi_sel = psisel(u.residues[res])

			phidat.addTimeseries(Timeseries.Dihedral(phi_sel))
			psidat.addTimeseries(Timeseries.Dihedral(psi_sel))

		numres = numres-2;
		#	Computes along whole trajectory
		phidat.compute(u.trajectory, skip=config['slice_val'])
		psidat.compute(u.trajectory, skip=config['slice_val'])
	
		#	Converts to nd-array and changes from [numRes,1,numSamples] to [numRes,numSamples]
		phidat =  array(phidat).reshape(phidat.shape[0],phidat.shape[2]);
		psidat =  array(psidat).reshape(psidat.shape[0],psidat.shape[2]);
		
		"""	Data stored as  | sin(phi) |---
							| cos(phi) |---
							| sin(psi) |---
							| cos(psi) |---"""

		dihedral_dat[0::2,:] = phidat
		dihedral_dat[1::2,:] = phidat
		
		if i == start_traj:
			fulldat = np.memmap('dihedral_data.array', dtype='float64', mode='w+', shape=(numres*2, trajlen/config['slice_val']))
			fulldat[:,:] = dihedral_dat
		else:
			fulldat = mmap_concat(fulldat, dihedral_dat);
	
	#	determining % time exhibiting anharmonicity
	anharm = np.zeros((2,numres));
	for i in range(2):
		for j in range(numres):
			tmp = ((fulldat[i::2,:])[j])
			median = np.median(tmp);
			stddev = np.std(tmp);
			anharm[i,j] = float( np.sum( (np.abs(tmp - median) > 2*stddev) ) ) / fulldat.shape[1];

	if val.save: np.save('savefiles/dih_anharm_%s.npy' %(config['pname']), anharm );

def jade_calc(config, filename, mapshape, val):
	
	if val.debug:	
		avgCoords = numpy.mean(coords, 1); 
		print avgCoords;
		print 'avgCoords: ', numpy.shape(avgCoords);
	
	#==========================================================================	
	#	Setup to determine proper ICA dimensionality
	if val.setup:
		[pcas,pcab] = numpy.linalg.eig(numpy.cov(coords));
		si = numpy.argsort(-pcas.ravel());
		pcaTmp = pcas;
		pcas = numpy.diag(pcas);
		pcab = pcab[:,si];
		
		fig = plt.figure();
		ax = fig.add_subplot(111);
		y = numpy.cumsum(pcaTmp.ravel()/numpy.sum(pcaTmp.ravel()));
		ax.plot(y*100);
		ax.set_xlabel('Number of Principal Components');
		ax.set_ylabel('Percent of Total Variance Preserved');
		ax.set_title('Variance of Principal Components');
		if val.verbose: print('Cov. Matrix spectrum cum. sum.');
		plt.show();
		a = input('Enter desired ICA dimension (enter -1 for default): ');
		if (a > 0):
			config['icadim'] = a;
	#	End ICA Setup
	#==========================================================================

	# some set up for running JADE
	subspace = config['icadim']; # number of IC's to find (dimension of PCA subspace)
	
	#	Performs jade and saves if main
	coords.flush();
	icajade = jadeR(filename, mapshape, val, subspace);
	if __name__ == '__main__' and (val.save): np.save('savefiles/icajade_%s_%i.npy' %(config['pname'], config['icadim']), icajade) 

	if val.debug: print 'icajade: ', numpy.shape(icajade);

	#	Performs change of basis
	icafile = path.join('./.memmapped','icacoffs.array');
	icacoffs = np.memmap(icafile, dtype='float64', mode='w+', shape=(config['icadim'],numsamp) );
	icacoffs[:,:] = icajade.dot(coords)
	icacoffs.flush();
	if val.debug: print 'icacoffs: ', numpy.shape(icacoffs);
	if (val.save) and __name__ == '__main__': np.save('savefiles/icacoffs_%s_%i.npy' %(config['pname'], config['icadim']), icacoffs[:,:]) 
	
	if val.graph:	
		fig = plt.figure();
		ax = fig.add_subplot(111, projection='3d');
		ax.scatter(icacoffs[0,::10], icacoffs[1,::10], icacoffs[2,::10], marker='o', c=[0.6,0.6,0.6]); 
		print 'First 3 Dimensions of Icacoffs';
		plt.show();

	#	Returns icajade matrix, ica filename, and the shape.
	return icajade, icafile, icacoffs.shape;


if __name__ == '__main__':
	parser = argparse.ArgumentParser()
	parser.add_argument('-g', action='store_true', dest='graph', default=False, help='Shows graphs.')
	parser.add_argument('-v', action='store_true', dest='verbose', default=False, help='Runs program verbosely.')
	parser.add_argument('-s', '--save', action='store_true', dest='save', default=False, help='Saves important matrices.')
	parser.add_argument('-d', '--debug', action='store_true', dest='debug', default=False, help='Prints debugging help.')
	parser.add_argument('--setup', action='store_true', dest='setup', default=False, help='Runs setup calculations: Cum. Sum. of cov. spectrum\nand unit radius neighbor search.')
	parser.add_argument('--single', action='store_true', dest='single', default=False, help='Runs jade w/ single precision. NOT recommended.')
	parser.add_argument('--smart', action='store_true', dest='smart', default=False, help='Runs jade using an alternative diagonalization setup. Refer to Cardoso\'s code for more details.')

	values = parser.parse_args()
	if values.debug: values.verbose = True;

#	Config settings -- only here if dQAA is called directly from python
	config = {};
	config['numOfTraj'] = 1;
	config['icadim'] = 40;
	config['pname'] = 'PROTEIN';	#	Edit to fit your protein name
	config['startRes'] = 0;			# 	excludes first
	config['endRes'] = -2;			#	excludes last
	qaa(config, values);
