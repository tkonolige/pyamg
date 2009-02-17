"""Compatible Relaxation"""

__docformat__ = "restructuredtext en"

from numpy import array, dot, multiply, power, sqrt, sum, ones, arange, \
        abs, inf, ceil, zeros, where, bool
from numpy.random import rand
from scipy.linalg import norm
from scipy.sparse import isspmatrix, csr_matrix, spdiags

from pyamg.relaxation import gauss_seidel

__all__ = ['CR','binormalize']

def CR(S, method='habituated',maxiter=20):
    """Use Compatible Relaxation to compute a C/F splitting 

    Parameters
    ----------
    S : csr_matrix
        sparse matrix (n x n) usually matrix A of Ax=b
    method : {'habituated','concurrent'}
        Method used during relaxation:
            - concurrent: GS relaxation on F-points, leaving e_c = 0
            - habituated: full relaxation, setting e_c = 0
    maxiter : int
        maximum number of outer iterations (lambda)

    Returns
    -------
    splitting : array
        C/F list of 1's (coarse pt) and 0's (fine pt) (n x 1)
   
    References
    ----------
    .. [Liv2004] Livne, O.E., "Coarsening by compatible relaxation."
       Numer. Linear Algebra Appl. 11, No. 2-3, 205-227 (2004).


    Examples
    --------
    >>> from numpy import linspace, meshgrid
    >>> from pyamg import poisson
    >>> from pyamg.classical.cr import CR
    >>> from pylab import imshow, show
    >>> n = 20
    >>> A = poisson((n,n),format='csr')
    >>> splitting = CR(A)
    >>> imshow(splitting.reshape((n,n)),interpolation='nearest')
    >>> show()
    """
    # parameters (paper notation)
    ntests = 3      # (nu) number of random tests to do per iteration
    nrelax = 4      # (eta) number of relaxation sweeps per test

    smagic = 1.0    # (s) parameter in [1,5] to account for fillin 
    gamma = 1.5     # (gamma) cycle index.  use 1.5 for 2d
    G = 30          # (G) number of equivalence classes (# of bins)
    tdepth = 1      # (t) drop depth on parse of L bins
    delta = 0       # (delta) drop threshold on parse of L bins
    alphai = 0.25   # (alpha_inc) quota increase

    # initializaitons    
    alpha = 0.0     # coarsening ratio, quota
    beta = inf      # quality criterion
    beta1 = inf     # quality criterion, older
    beta2 = inf     # quality criterion, oldest
    n=S.shape[0]    # problem size
    nC = 0          # number of current Coarse points
    rhs = zeros((n,1)); # rhs for Ae=0

    if not isspmatrix(S): raise TypeError('expecting sparse matrix')

    S = binormalize(S)
    
    splitting = zeros( (S.shape[0],1), dtype=int )
   
    # out iterations ---------------
    for m in range(0,maxiter):

        mu = 0.0        # convergence rate
        E = zeros((n,1))  # slowness measure

        # random iterations ---------------
        for k in range(0,ntests):

            e  = 0.5*( 1 + rand(n,1))
            e[splitting>0] = 0

            enorm = norm(e)

            # relaxation iterations ---------------
            for l in range(0,nrelax):

                if method == 'habituated':
                    gauss_seidel(S,e,zeros((n,1)),iterations=1)
                    e[splitting>0]=0
                elif method == 'concurrent':
                    raise NotImplementedError, 'not implemented: need an F-smoother'
                else:
                    raise NotImplementedError, 'method not recognized.  need habituated or concurrent'

                enorm_old = enorm
                enorm     = norm(e)

                if enorm <= 1e-14:
                    # break out of loops
                    ntests = k
                    nrelax = l
                    maxiter = m
            # end relax

            # check slowness
            E = where( abs(e)>E, abs(e), E )

            # update convergence rate
            mu = mu + enorm/enorm_old
        # end random tests
        mu = mu/ntests

        # work
        alpha = float(nC)/n

        W = (1 + (smagic-1)*gamma*alpha)/(1-gamma*alpha)
        
        # quality criterion
        beta2 = beta1
        beta1 = beta
        beta = power(max([mu, 0.1]), 1.0 / W)
        
        # check if we're doing well
        if (beta>beta1 and beta1>beta2) or m==(maxiter-1) or max(E)<1e-13:
            return splitting.ravel()

        # now add points
        #
        # update limit on addtions to splitting (C)
        if alpha < 1e-13:
            alpha=0.25
        else:
            alpha = (1-alphai) * alpha + alphai * (1/gamma)

        nCmax = ceil( alpha * n )

        L = ceil( G * E / E.max() ).ravel()

        binid=G

        # add whole bins (and tdepth nodes) at a time
        u = zeros((n,1))
        while nC < nCmax:
            if delta > 0:
                raise NotImplementedError
            if tdepth != 1:
                raise NotImplementedError

            (roots,) = where(L==binid)

            for root in roots:
                if L[root]>=0:
                    cols = S[root,:].indices
                    splitting[root] = 1    # add roots
                    nC += 1
                    L[cols]=-1
            binid -= 1

            #L[troots] = -1          # mark t-rings visited
            #u[:]=0.0
            #u[roots] = 1.0
            #for depth in range(0,tdepth):
            #    u = abs(S) * u
            #(troots,tmp) = where(u>0)

    return splitting.ravel()

def binormalize( A, tol=1e-5, maxiter=10):
    """Binormalize matrix A.  Attempt to create unit l_1 norm rows.

    Parameters
    ----------
    A : csr_matrix
        sparse matrix (n x n)
    tol : float
        tolerance
    x : array
        guess at the diagonal
    maxiter : int
        maximum number of iterations to try

    Returns
    -------
    C : csr_matrix
        diagonally scaled A, C=DAD

    Notes
    -----
        - BIN Algorithm to binormalize a matrix following:

          Livne, Golub, Scaling by Binormalization, 2003

        - Goal: Scale A so that l_1 norm of the rows are equal to 1:
                o B=DAD
                o want row sum of B = 1
                o easily done with tol=0 if B=DA, but this is not symmetric
                o algorithm is O(N log (1.0/tol))

    Examples
    --------
    >>> from pyamg import poisson
    >>> from pyamg.classical import binormalize
    >>> A = poisson((10,),format='csr')
    >>> C = binormalize(A)
    >>> print C.multiply(C).sum(axis=1)

    """
    if not isspmatrix(A): 
        raise TypeError('expecting sparse matrix A')

    if A.dtype==complex:
        raise NotImplementedError('complex A not implemented')

    n  = A.shape[0]
    it = 0
    x = ones((n,1)).ravel()

    # 1.
    B = A.multiply(A).tocsc()  # power(A,2) inconsistent for numpy, scipy.sparse
    d=B.diagonal().ravel()
    
    # 2.
    beta    = B * x
    betabar = (1.0/n) * dot(x,beta)
    stdev = rowsum_stdev(x,beta)

    #3
    while stdev > tol and it < maxiter:
        for i in range(0,n):
            # solve equation x_i, keeping x_j's fixed
            # see equation (12)
            c2 = (n-1)*d[i]
            c1 = (n-2)*(beta[i] - d[i]*x[i])
            c0 = -d[i]*x[i]*x[i] + 2*beta[i]*x[i] - n*betabar
            if (-c0 < 1e-14):
                print 'warning: A nearly un-binormalizable...'
                return A
            else:
                # see equation (12)
                xnew = (2*c0)/(-c1 - sqrt(c1*c1 - 4*c0*c2))
            dx = xnew - x[i]

            # here we assume input matrix is symmetric since we grab a row of B
            # instead of a column
            ii = B.indptr[i]
            iii = B.indptr[i+1]
            dot_Bcol = dot(x[B.indices[ii:iii]],B.data[ii:iii])

            betabar = betabar + (1.0/n)*dx*(dot_Bcol + beta[i] + d[i]*dx)
            beta[B.indices[ii:iii]] += dx*B.data[ii:iii]

            x[i] = xnew

        stdev = rowsum_stdev(x,beta)
        it+=1

    # rescale for unit 2-norm
    d = sqrt(x)
    D = spdiags( d.ravel(), [0], n,n)
    C = D * A * D
    C = C.tocsr()
    beta = C.multiply(C).sum(axis=1)
    scale = sqrt((1.0/n) * sum(beta))
    return (1/scale)*C


def rowsum_stdev(x,beta):
    """Compute row sum standard deviation

    Compute for approximation x, the std dev of the row sums
    s(x) = ( 1/n \sum_k  (x_k beta_k - betabar)^2 )^(1/2)
    with betabar = 1/n dot(beta,x)

    Parameters
    ----------
    x : array
    beta : array

    Returns
    -------
    s(x)/betabar : float

    Notes
    -----
    equation (7) in Livne/Golub

    """
    n=x.size
    betabar = (1.0/n) * dot(x,beta)
    stdev   = sqrt((1.0/n)*sum(power(multiply(x,beta) - betabar,2)))
    return stdev/betabar
