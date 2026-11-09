import numpy as np
KE=3.19595**4
# reference panel: cement render 20 mm on concrete
H,E,RHO,NU = 0.020, 18e9, 2000.0, 0.20
D = E*H**3/(12*(1-NU**2))
def f1(k,a):
    return (1/(2*np.pi))*np.sqrt((D*KE/a**4 + k)/(RHO*H))
print("D = %.4e N.m  ->  A (1/a^2 coefficient) = %.4e Hz.m^2 = %.4e Hz.cm^2"
      % (D, (1/(2*np.pi))*np.sqrt(D*KE/(RHO*H)), (1/(2*np.pi))*np.sqrt(D*KE/(RHO*H))*1e4))
print("\nbonded baseline f1 (k=9e11 Pa/m), a -> inf:", f1(9e11,1.0), "Hz  <-- ABOVE the 16 kHz band")
print("\ndebond diameter -> f1 by grade:")
print(f"{'dia[cm]':>8}{'r[m]':>7}{'G0(k=9e11)':>12}{'G1(k=3e8)':>11}{'G2(k=0)':>10}")
for d in (3,5,10,15,20,30,40):
    a=0.005*d
    print(f"{d:8.0f}{a:7.3f}{f1(9e11,a):12.0f}{f1(3e8,a):11.0f}{f1(0,a):10.0f}")
print("\nwhen does k matter?  crossover where k = D*alpha^4/a^4")
for d in (10,20,30,40):
    a=0.005*d
    print(f"  dia {d:2d} cm: D*alpha^4/a^4 = {D*KE/a**4:.3e} Pa/m")
print("\n=> G1 partial debond (k=3e8) differs appreciably from G2 only for dia >= ~20 cm")
print("\nin-band peak of the BONDED control comes from the broadband strike transient,")
print("not from a mode -- so it is broad and low. Model it as lognormal(700 Hz, sd 0.35).")
