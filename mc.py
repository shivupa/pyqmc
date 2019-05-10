import numpy as np
from pyscf import lib, gto, scf
from slater import PySCFSlaterRHF
from energy import energy


def initial_guess(mol,nconfig,r=1.0):
    """ Generate an initial guess by distributing electrons near atoms
    proportional to their charge."""
    nelec=np.sum(mol.nelec)
    epos=np.zeros((nconfig,nelec,3))
    wts=mol.atom_charges()
    wts=wts/np.sum(wts)

    ### This is not ideal since we loop over configs 
    ### Should figure out a way to throw configurations
    ### more efficiently.
    for c in range(nconfig):
        count=0
        for s in [0,1]:
            neach=np.floor(mol.nelec[s]*wts)
            nassigned=np.sum(neach)
            nleft=mol.nelec[s]*wts-neach
            tot=int(np.sum(nleft))
            gets=np.random.choice(len(wts),p=nleft,size=tot,replace=False) 
            for i in gets:
                neach[i]+=1
            for n,coord in zip(neach,mol.atom_coords()):
                for i in range(int(n)):
                    epos[c,count,:]=coord+r*np.random.randn(3)
                    count+=1
    return epos
    
def initial_guess_vectorize(mol,nconfig,r=1.0):
    """ Generate an initial guess by distributing electrons near atoms
    proportional to their charge."""
    nelec=np.sum(mol.nelec)
    epos=np.zeros((nconfig,nelec,3))
    wts=mol.atom_charges()
    wts=wts/np.sum(wts)

    # assign electrons to atoms based on atom charges
    # assign the minimum number first, and assign the leftover ones randomly
    # this algorithm chooses atoms *with replacement* to assign leftover electrons

    for s in [0,1]:
        neach=np.array(np.floor(mol.nelec[s]*wts),dtype=int) # integer number of elec on each atom
        nleft=mol.nelec[s]*wts-neach # fraction of electron unassigned on each atom
        nassigned=np.sum(neach) # number of electrons assigned
        totleft=int(mol.nelec[s]-nassigned) # number of electrons not yet assigned
        bins=np.cumsum(nleft)/totleft
        inds = np.digitize(np.random.random((nconfig,totleft)), bins)
        ind0=s*mol.nelec[0]
        epos[:,ind0:ind0+nassigned,:] = np.repeat(mol.atom_coords(),neach,axis=0)[np.newaxis] # assign core electrons
        epos[:,ind0+nassigned:ind0+mol.nelec[s],:] = mol.atom_coords()[inds] # assign remaining electrons
    epos+=r*np.random.randn(*epos.shape) # random shifts from atom positions
    return epos

def vmc(mol,wf,coords,nsteps=10000,tstep=0.5,accumulators=None):
    if accumulators is None:
        accumulators={'energy':energy } 
    nconf=coords.shape[0]
    nelec=np.sum(mol.nelec)
    df=[]
    wf.recompute(coords)
    for step in range(nsteps):
        print("step",step)
        acc=[]
        for e in range(nelec):
            newcoorde=coords[:,e,:]+np.random.normal(scale=tstep,size=(nconf,3))
            ratio=wf.testvalue(e,newcoorde)
            accept=ratio**2 > np.random.rand(nconf)
            coords[accept,e,:]=newcoorde[accept,:]
            wf.updateinternals(e,coords[:,e,:],accept)
            acc.append(np.mean(accept))
        avg={}
        for k,accumulator in accumulators.items():
            dat=accumulator(mol,coords,wf)
            for m,res in dat.items():
                avg[k+m]=np.mean(res,axis=0)
        avg['acceptance']=np.mean(acc)
        df.append(avg)
    return df #should return back new coordinates
    

def test():
    import pandas as pd
    
    mol = gto.M(atom='Li 0. 0. 0.; Li 0. 0. 1.5', basis='cc-pvtz',unit='bohr',verbose=5)
    mf = scf.RHF(mol).run()
    nconf=5000
    wf=PySCFSlaterRHF(nconf,mol,mf)
    coords = initial_guess(mol,nconf) 
    def dipole(mol,coords,wf):
        return {'vec':np.sum(coords[:,:,:],axis=1) } 
    df=vmc(mol,wf,coords,nsteps=100,accumulators={'energy':energy, 'dipole':dipole } )

    df=pd.DataFrame(df)
    df.to_csv("data.csv")
    warmup=30
    print('mean field',mf.energy_tot(),'vmc estimation', np.mean(df['energytotal'][warmup:]),np.std(df['energytotal'][warmup:]))
    print('dipole',np.mean(np.asarray(df['dipolevec'][warmup:]),axis=0))
    
def test_init_guess_timing():
    import time
    mol = gto.M(atom='Li 0. 0. 0.; Li 0. 0. 1.5', basis='cc-pvtz',unit='bohr',verbose=5)
    mf = scf.RHF(mol).run()
    nconf=5000
    wf=PySCFSlaterRHF(nconf,mol,mf)
    for j in range(5):
        for i,func in enumerate([initial_guess, initial_guess_vectorize]):
            start = time.time()
            coords = func(mol,nconf) 
            print(time.time()-start)
    

if __name__=="__main__":
    import cProfile, pstats, io
    from pstats import SortKey
    pr = cProfile.Profile()
    pr.enable()
    test()
    pr.disable()
    s = io.StringIO()
    sortby = SortKey.CUMULATIVE
    ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
    ps.print_stats()
    print(s.getvalue())
    
