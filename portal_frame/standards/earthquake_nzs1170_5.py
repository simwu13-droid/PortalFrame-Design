"""NZS 1170.5:2004 Earthquake Loading — Placeholder.

Planned scope:
- NZ_HAZARD_FACTORS dict (19 NZ locations -> Z values)
- _CH_TABLE spectral shape factor table (5 soil classes, Table 3.1)
- spectral_shape_factor(T, soil_class) using lerp
- calculate_earthquake_forces(geom, loads, eq) -> T1, Ch, k_mu, Cd, Wt, V, F_node

Key formulas (NZS 1170.5:2004):
    V = Cd(T1) * Wt
    Cd(T1) = Ch(T1) * Z * R * N(T,D) * Sp / k_mu
    k_mu: if T1 >= 0.7s -> k_mu = mu; if T1 < 0.7s -> k_mu = (mu-1)*T1/0.7 + 1
    T1 = 1.25 * 0.085 * h_n^0.75  (steel MRF, Clause 4.1.2.1)
    Floor: Cd(T1) >= max(0.03, Z*R*0.02)
"""
