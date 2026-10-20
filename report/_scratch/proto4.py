import numpy as np
E,h,rho,nu=18e9,0.020,2000.0,0.20
D=E*h**3/(12*(1-nu**2)); ALNUM=3.19595; T=300e-6; QFAC=9.0
F=np.fft.rfftfreq(1024,1/48000.0)
AF=np.cos(np.pi*F*T/2.0)/(1.0-(F*T)**2); SQ_F2=np.sqrt(AF**2)
BG=0.35/(1.0+(F/500.0)**0.7)
BAND=(F>=300.0)&(F<=15000.0); LOW=BAND&(F<1000.0); HIGH=BAND&(F>=1000.0)
def f1_of(size,k):
    fm=0.0 if size<=0 else float(np.sqrt(D*(ALNUM/(size/200.0))**4/(rho*h))/(2*np.pi))
    ff=float(np.sqrt(k/(rho*h))/(2*np.pi))
    return float(np.hypot(fm,ff))
def tap(rng,size,f1,rad,bg):
    bgv=bg*BG
    if f1>20000.0 or f1<=0.0: H=np.abs(bgv)
    else: H=np.abs(bgv+rad/((1.0-(F/f1)**2)+1j*(F/(f1*QFAC))))
    S=SQ_F2*H*np.exp(rng.normal(0.0,0.05,F.size))
    fb,Sb=F[BAND],S[BAND]
    fpk=float(fb[int(np.argmax(Sb))])
    cen=float(np.sum(fb*Sb)/np.sum(Sb))
    br=float(np.sum(Sb[LOW[BAND]]**2))/float(np.sum(Sb[HIGH[BAND]]**2))
    tau=1000.0*QFAC/(np.pi*f1) if f1>0 else float('inf')
    if not (3.0<=tau<=60.0): tau=-1.0
    return fpk,cen,br,tau
KS={"G0":9.0e11,"G1":1.0e10,"G2":0.0}
SEV={"G0":0.0,"G1":0.45,"G2":0.95}
def gen(seed=20261016,n_panels=12,taps=5):
    rng=np.random.default_rng(seed)
    plan=[("G0",0)]*3+[(g,s) for s in (3,5,10,15,20) for g in ("G2","G1")]
    rows=[]
    for pi in range(n_panels):
        rad_eff=3.0*float(np.exp(rng.normal(0.0,0.07)))
        bg_eff=float(np.exp(rng.normal(0.0,0.05)))
        for g,s in plan:
            sf=1.0 if s==0 else float(np.clip(s/10.0,0.30,1.0))
            f1=f1_of(s,KS[g])
            for tp in range(taps):
                rows.append((g,s)+tap(rng,s,f1,rad_eff*sf,bg_eff))
    return rows
rows=gen()
import collections
d=collections.defaultdict(list)
for g,s,fpk,cen,br,tau in rows: d[(g,s)].append((fpk,cen,br,tau))
print("%-3s %-5s %5s %11s %11s %13s %8s %7s"%("g","size","n","med_fpk","med_cen","med_band_ratio","med_tau","sent%"))
for g in ("G0","G1","G2"):
    for s in ((0,) if g=="G0" else (3,5,10,15,20)):
        A=np.array(d[(g,s)]); fpk,cen,br,tau=A.T
        print("%-3s %-5d %5d %11.1f %11.1f %13.5g %8.3f %6.0f%%"%(g,s,len(A),np.median(fpk),np.median(cen),np.median(br),np.median(tau),100*np.mean(tau<0)))
        print("     fpk range %.0f..%.0f  uniq=%d"%(fpk.min(),fpk.max(),len(np.unique(fpk))))
