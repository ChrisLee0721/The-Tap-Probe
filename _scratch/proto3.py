import numpy as np
E,h,rho,nu=18e9,0.020,2000.0,0.20
D=E*h**3/(12*(1-nu**2))
ALNUM=3.19595; T=300e-6; QFAC=9.0
F=np.fft.rfftfreq(1024,1/48000.0)
AF=np.cos(np.pi*F*T/2.0)/(1.0-(F*T)**2)
SQ_F2=np.sqrt(AF**2)
BG_SHAPE=0.35/(1.0+(F/500.0)**0.7)
MODE_SHAPE=1.0/((1.0-(F/1.0)**2) if False else 1.0)  # unused
TAU_LO,TAU_HI=3.0,60.0
BAND=(F>=300.0)&(F<=15000.0)
LOW=BAND&(F<1000.0); HIGH=BAND&(F>=1000.0)
def f1_of(size,k):
    fm = 0.0 if size<=0 else float(np.sqrt(D*(ALNUM/(size/200.0))**4/(rho*h))/(2*np.pi))
    ff = float(np.sqrt(k/(rho*h))/(2*np.pi))
    return float(np.hypot(fm,ff))
def one_tap(size,f1,rad,bg,pf,pk):
    bgv=bg*BG_SHAPE
    if f1>20000.0 or f1<=0.0:
        H=np.abs(bgv)
    else:
        H=np.abs(bgv+rad/((1.0-(F/f1)**2)+1j*(F/(f1*QFAC))))
    S=np.exp(pf)*SQ_F2*H
    S=S*np.exp(pk*np.random.default_rng().normal(0.0,0.05,S.size)) if False else S
    return S
# vectorised-ish single tap with given rng
def tap(rng,size,f1,rad,bg,pf,pk):
    bgv=bg*BG_SHAPE
    if f1>20000.0 or f1<=0.0:
        H=np.abs(bgv)
    else:
        H=np.abs(bgv+rad/((1.0-(F/f1)**2)+1j*(F/(f1*QFAC))))
    S=np.exp(pf)*SQ_F2*H
    S=S*np.exp(rng.normal(0.0,float(pk),S.size))
    fb, Sb = F[BAND], S[BAND]
    fpeak=float(fb[int(np.argmax(Sb))])
    cent=float(np.sum(fb*Sb)/np.sum(Sb))
    br=float(np.sum(Sb[LOW[BAND]]**2))/float(np.sum(Sb[HIGH[BAND]]**2))
    tau=1000.0*QFAC/(np.pi*f1) if f1>0 else float('inf')
    if not (TAU_LO<=tau<=TAU_HI): tau=-1.0
    return fpeak,cent,br,tau
KS={"G0":9.0e11,"G1":1.0e10,"G2":0.0}
SEV={"G0":0.0,"G1":0.45,"G2":0.95}
def gen(seed=20261016,n_panels=12,taps=5):
    rng=np.random.default_rng(seed)
    for pi in range(n_panels):
        rad_eff=3.0*float(np.exp(rng.normal(0.0,0.07)))
        bg_eff=1.0*float(np.exp(rng.normal(0.0,0.05)))
        S=None
        plan=[("G0",0)]*3+[(g,s) for s in (3,5,10,15,20) for g in ("G2","G1")]
        for loc,(g,s) in enumerate(plan):
            sf=1.0 if s==0 else float(np.clip(s/10.0,0.30,1.0))
            f1=f1_of(s,KS[g]); rad=rad_eff*sf; bg=bg_eff
            for tp in range(taps):
                r=tap(rng,s,f1,rad,bg,float(rng.normal(0.0,0.06)),float(rng.normal(0.0,0.05)))
                if S is None: S={}
                key=(g,s); S.setdefault(key,[]).append(r)
    return S
S=gen()
print("%-4s %-4s %6s %10s %10s %12s %10s %8s"%("g","size","n","med_fpk","med_cen","med_band","med_tau","%tau_sent"))
for g in ("G0","G1","G2"):
    for s in ((0,) if g=="G0" else (3,5,10,15,20)):
        A=np.array(S[(g,s)])
        fpk=A[:,0];cen=A[:,1];br=A[:,2];tau=A[:,3]
        print("%-4s %-4d %6d %10.1f %10.1f %12.5g %10.3f %8.0f%%"%(g,s,len(fpk),np.median(fpk),np.median(cen),np.median(br),np.median(tau),100*np.mean(tau<0)))
        print("      fpk: %s"%(" ".join("%.0f"%v for v in np.sort(fpk)[:20])))
