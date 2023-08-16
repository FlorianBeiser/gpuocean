# -*- coding: utf-8 -*-

"""
This software is a part of GPU Ocean.

Copyright (C) 2018  SINTEF Digital

This python class implements a DrifterCollection living on the CPU.

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""


import numpy as np

from gpuocean.utils import Common
from gpuocean.drifters import CPUDrifterCollection

class MLDrifterCollection(CPUDrifterCollection.CPUDrifterCollection):
    """
    Class holding a collection of drifters for a 
    """ 
    def __init__(self, numDrifters, ensemble_size, observation_variance=0.01,
                 boundaryConditions=Common.BoundaryConditions(), 
                 initialization_cov_drifters=None,
                 domain_size_x=1.0, domain_size_y=1.0):
        """
        Creates a collection of drifters suitable for multi-level (ML) ensembles.

        Most relevant parameters
        numDrifters: number of drifters represented in the collection
        ensemble_size: number of realization per drifter. 
        boundaryConditions: BoundaryConditions object, relevant during drift
        domain_size_{x,y}: size of computational domain in meters
        """
        
        # Call parent constructor
        super(MLDrifterCollection, self).__init__(numDrifters*ensemble_size,
                                         observation_variance=observation_variance,
                                         boundaryConditions=boundaryConditions,
                                         domain_size_x=domain_size_x, 
                                         domain_size_y=domain_size_y)
        
        self.ensemble_size = ensemble_size
        self.num_unique_drifters = numDrifters
        
        # To initialize drifters uniformly (default behaviour of the other DrifterCollections)
        # we need to make a temporary drifter object
        initializedDrifters = CPUDrifterCollection.CPUDrifterCollection(numDrifters, 
                                                                        boundaryConditions=boundaryConditions,
                                                                        initialization_cov_drifters=initialization_cov_drifters,
                                                                        domain_size_x=domain_size_x,
                                                                        domain_size_y=domain_size_y)
        
        # drifter data is organized by storing the position of all ensemble members representing the same drifter
        # in consecutive blocks.
        init_positions = initializedDrifters.getDrifterPositions()
        self.positions[:-1, :] = np.repeat(init_positions, self.ensemble_size, axis=0)
    
    # Mappings between drifters and ensemble members
    def expandDrifterPositions(self, pos):
        """
        Given a position per unique drifter as input, we return an array with an ensemble of the exact same position
        input.shape: (numDrifters, 2), output.shape: (numDrifters*ensemble_size, 2)
        """
        return np.repeat(pos, self.ensemble_size, axis=0)
    
    def getDrifterPositionsForDrifter(self, drifter_index):
        """
        Gives the positions corresponding to the give drifter.
        Returns array of shape (ensemble_size, 2)
        """
        assert(drifter_index >= 0), "drifter_index must be positive, but got " +str(drifter_index)
        assert(drifter_index < self.num_unique_drifters), "drifter_index must be smaller than number of unique drifters ("+str(self.num_unique_drifters)+"), but got " +str(drifter_index)
        
        pos = self.positions[drifter_index*self.ensemble_size:(drifter_index + 1)*self.ensemble_size, :].copy()
        assert(pos.shape == (self.ensemble_size, 2)), "Expected data for "+str(self.ensemble_size)+"drifters, but only got "+pos.shape[0]
        return pos

    def getDrifterPositionsForEnsembleMember(self, ensemble_member):
        """
        Gives the positions of all drifters for a given ensemble member
        Returns array of shape (num_unique_drifters, 2)
        """
        assert(ensemble_member >= 0), "ensemble_member must be positive, but got " +str(ensemble_member)
        assert(ensemble_member < self.ensemble_size), "drifter_index must be smaller than the ensemble size ("+str(self.ensemble_size)+"), but got " +str(ensemble_member)

        pos = self.positions[ensemble_member:-1:self.ensemble_size, :].copy()
        assert(pos.shape == (self.num_unique_drifters, 2)), "Expected data for "+str(self.num_unique_drifters)+"drifters, but only got "+pos.shape[0]
        return pos

    # Overloading other functions

    def setDrifterPositions(self, newDrifterPositions):
        """ 
        new fixed positions for drifters
        """
        if newDrifterPositions.shape[0] == self.numDrifters:
            return super().setDrifterPositions(newDrifterPositions)
        elif newDrifterPositions.shape[0] == self.num_unique_drifters:
            return super().setDrifterPositions(self.expandDrifterPositions(newDrifterPositions))
        
    def drift(self, u_field, v_field, dx, dy, dt, 
              x_zero_ref=0, y_zero_ref=0, 
              u_stddev=None, v_stddev=None, sensitivity=1.0):
        """
        Evolve all drifters with a simple Euler step.
        Velocities are interpolated from the fields
        
        {x,y}_zero_ref points to which cell has face values {x,y} = 0. 
        {u,v}_stddev are fields and provide a random walk
        """

        assert(u_stddev is not None and v_stddev is not None), "u_stddev and v_stddev must be provided for the MLDrifterCollection class to make sense"

        if self.boundaryConditions.isPeriodic() and x_zero_ref == 0 and y_zero_ref == 0:
            # Ensure that we have a periodic halo so that we can interpolate through
            # periodic boundary
            u_field  = self._expandPeriodicField(u_field)
            v_field  = self._expandPeriodicField(v_field)
            u_stddev = self._expandPeriodicField(u_stddev)
            v_stddev = self._expandPeriodicField(v_stddev)
            x_zero_ref = 1
            y_zero_ref = 1

        self.driftFromVelocities(u_field, v_field, dx, dy, dt, 
                   x_zero_ref=x_zero_ref, y_zero_ref=y_zero_ref, 
                   u_stddev=u_stddev, v_stddev=v_stddev, sensitivity=sensitivity)
        
    def _expandPeriodicField(self, field):
        """
        Put a halo of periodic values of one grid cell around the given field
        """
        ny, nx = field.shape
        exp_field = np.zeros((ny+2, nx+2))
        exp_field[1:-1, 1:-1] = field
        exp_field[ 0,  :] = exp_field[-2,  :]
        exp_field[-1,  :] = exp_field[ 1,  :]
        exp_field[ :,  0] = exp_field[ :, -2]
        exp_field[ :, -1] = exp_field[ :,  1]
        return exp_field
