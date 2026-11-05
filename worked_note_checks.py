"""Narrow independent arithmetic/numerical checks, not a general math grader."""
from fractions import Fraction
import math
import random


def integrate(function,lo=0.,hi=1.,panels=2000):
    if panels%2:raise ValueError('Simpson panels must be even')
    h=(hi-lo)/panels
    return h/3*(function(lo)+function(hi)+sum((4 if i%2 else 2)*function(lo+i*h) for i in range(1,panels)))


def checks():
    weights=[[Fraction(1,2),Fraction(1,3),Fraction(1,6)],[Fraction(1,3)]*3,[Fraction(1,6),Fraction(1,6),Fraction(2,3)]]
    sums=[sum(w) for w in weights];variances=[sum(a*a for a in w) for w in weights]
    linear={'method':'exact rational arithmetic','weight_sums':[str(x) for x in sums],
            'variance_coefficients':[str(x) for x in variances],
            'passed':sums==[1,1,1] and variances==[Fraction(7,18),Fraction(1,3),Fraction(1,2)]}
    moments={}
    for name,density in [('maximum',lambda y:3*y*y),('minimum',lambda y:3*(1-y)**2)]:
        moments[name]=[integrate(lambda y:density(y)*y**k) for k in (0,1,2)]
    vmax=(4/3)**2*(moments['maximum'][2]-moments['maximum'][1]**2)
    vmin=16*(moments['minimum'][2]-moments['minimum'][1]**2)
    uniform={'method':'Simpson integration of order-statistic densities on [0,1]',
             'moments':moments,'variance_coefficients':[vmax,vmin],
             'passed':max(abs(vmax-1/15),abs(vmin-3/5),abs(moments['maximum'][0]-1),abs(moments['minimum'][0]-1))<1e-10}
    a,b,k,observations=2,3,2,[2,4,5];A=a+len(observations)*k;B=b+sum(observations)-len(observations)*k
    # Direct binomial likelihood times unnormalised prior, integrated separately.
    def joint(p):
        return math.prod(math.comb(x-1,k-1)*p**k*(1-p)**(x-k) for x in observations)*p**(a-1)*(1-p)**(b-1)
    normalizer=integrate(joint)
    def beta(p):return math.exp(math.lgamma(A+B)-math.lgamma(A)-math.lgamma(B))*p**(A-1)*(1-p)**(B-1)
    error=max(abs(joint(p)/normalizer-beta(p)) for p in [.03,.17,.4,.6,.8,.95])
    mean=integrate(lambda p:p*joint(p))/normalizer
    conjugacy={'method':'direct likelihood-prior product quadrature vs normalized Beta density',
               'parameters':{'a':a,'b':b,'k':k,'observations':observations},'posterior_shapes':[A,B],
               'max_density_error':error,'posterior_mean':mean,
               'passed':error<1e-9 and abs(mean-A/(A+B))<1e-10}
    rng=random.Random(20261027);results=[];n=3;alpha=.05;draws=20000
    for theta in [-2.,0.,4.]:
        covered=0
        for _ in range(draws):
            sample=[theta+rng.expovariate(1.) for _ in range(n)];minimum=min(sample)
            lo=minimum+math.log(alpha)/n
            covered+=lo<=theta<=minimum
        results.append({'theta':theta,'n':n,'alpha':alpha,'draws':draws,'empirical_coverage':covered/draws})
    interval={'method':'fixed-seed simulation from individual shifted exponential observations',
              'results':results,'tolerance':.008,
              'passed':all(abs(r['empirical_coverage']-(1-alpha))<.008 for r in results)}
    return {'linear_weights':linear,'uniform_order_statistics':uniform,
            'negative_binomial_beta':conjugacy,'shifted_exponential_interval':interval}


if __name__=='__main__':
    import json
    print(json.dumps(checks(),ensure_ascii=False,indent=2))
