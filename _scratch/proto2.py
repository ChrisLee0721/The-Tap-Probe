import numpy as np
E,h,rho,nu=18e9,0.020,2000.0,0.20
D=E*h**3/(12*(1-nu**2))
alnum=3.19595; Tpred=300e-6; Q=9.0
f=np.fft.rfftfreq(1024,1/48000.0)
A=np.cos(np.pi*f*Tpred/2.0)/(1.0-(f*Tpred)**2)
F2=A**2
def f_mode(s):
    a=s/200.0
    return float(np.sqrt(D*(alnum/a)**4/(rho*h))/(2*np.pi))
def f_found(k): return float(np.sqrt(k/(rho*h))/(2*np.pi))
def f1(s,k):
    return float(np.hypot(f_mode(s) if s>0 else 0.0, f_found(k)))
def spec(f1v,rad,bgs=1.0):
    bg=bgs*0.35/(1.0+(f/500.0)**0.7)
    if f1v>20000.0 or f1v<=0.0:
        return np.sqrt(F2)*np.abs(bg)
    mode=rad/((1.0-(f/f1v)**2)+1j*(f/(f1v*Q)))
    return np.sqrt(F2)*np.abs(bg+mode)
BAND=(f>=300.0)&(f<=15000.0)
LOW=BAND&(f<1000.0); HIGH=BAND&(f>=1000.0)
for g,k in (("G0",9e11),("G1",1e10),("G2",0.0)):
    for s in ((0,) if g=="G0" else (3,5,10,15,20)):
        sf=1.0 if s==0 else float(np.clip(s/10.0,0.30,1.0))
        S=spec(f1(s,k),3.0*sf)
        fb=f[BAND];Sb=S[BAND]
        pk=fb[int(np.argmax(Sb))]
        cen=float(np.sum(fb*Sb)/np.sum(Sb))
        br=float(np.sum(Sb[LOW[BAND]]**2))/float(np.sum(Sb[HIGH[BAND]]**2))
        fv=f1(s,k)
        tau=1000*Q/(np.pi*fv) if fv>0 else float('inf')
        print("%s %2dcm f1=%9.1f fpk=%8.1f cen=%8.1f br=%10.4g tau=%7.3f %s"%(
            g,s,fv,pk,cen,br,tau,"SENTINEL" if not(3.0<=tau<=60.0) else "kept"))
