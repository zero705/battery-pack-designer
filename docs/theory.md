# Theory and equations

This page documents every equation the tool uses, so each number in a report can be
checked by hand. The worked example is an **8S2P pack of Samsung INR18650-30Q** cells,
using the values from the Samsung SDI cell specification (version 1.0):

| Cell parameter | Value | Datasheet item |
|---|---|---|
| Nominal voltage | 3.6 V | 3.2 Nominal voltage |
| Charge voltage | 4.2 V | 3.4 Rated charge |
| Discharge cut-off | 2.5 V | 3.8 Discharge cut-off voltage |
| Capacity | 2.95 Ah | 3.1 Minimum discharge capacity |
| Max continuous discharge | 15 A | 3.7 Max. continuous discharge |
| Max charge current | 4 A | 3.4 Rated charge |
| Resistance | 26 mOhm | 7.5 Initial internal impedance (AC 1 kHz, max) |
| Mass | 48.0 g | 3.9 Cell weight (max) |

## 1. Series and parallel

`S` cells in series add their voltages; `P` cells in parallel add their capacities and
currents. A pack written `SsPp` contains `S x P` cells.

| Quantity | Equation | 8S2P example |
|---|---|---|
| Cell count | `N = S * P` | 16 |
| Nominal voltage | `V_nom = S * V_cell,nom` | 8 x 3.6 = 28.8 V |
| Full-charge voltage | `V_max = S * V_cell,max` | 8 x 4.2 = 33.6 V |
| Cut-off voltage | `V_min = S * V_cell,cutoff` | 8 x 2.5 = 20.0 V |
| Capacity | `C = P * C_cell` | 2 x 2.95 = 5.90 Ah |
| Energy | `E = V_nom * C` | 28.8 x 5.90 = 169.9 Wh |
| Max continuous current | `I_max = P * I_cell,max` | 2 x 15 = 30 A |
| Max charge current | `I_chg = P * I_cell,chg` | 2 x 4 = 8 A |
| Cell mass | `m = N * m_cell` | 16 x 0.048 = 0.768 kg |
| Specific energy | `E / m` | 169.9 / 0.768 = 221 Wh/kg |

## 2. Internal resistance, voltage sag and heat

Series resistances add and parallel resistances divide:

```
R_pack = R_cell * S / P = 0.026 * 8 / 2 = 0.104 ohm
```

The pack is modelled as an ideal source at the nominal voltage behind `R_pack`. At a
constant load current `I`:

| Quantity | Equation | Example at 30 A |
|---|---|---|
| C-rate | `I / C` | 30 / 5.90 = 5.08C |
| Terminal voltage | `V = V_nom - I * R_pack` | 28.8 - 30 x 0.104 = 25.68 V |
| Output power | `P_out = V * I` | 25.68 x 30 = 770 W |
| Heat in the cells | `P_heat = I^2 * R_pack` | 30^2 x 0.104 = 93.6 W |
| Heat per cell | `P_heat / N` | 93.6 / 16 = 5.85 W |
| Ideal runtime | `C / I` | 5.90 / 30 = 0.197 h = 11.8 min |

Almost 6 W in a single 18650 is a lot: at its rated current a cell heats up quickly
without cooling. This is why continuous ratings, thermal design and temperature
sensing matter.

**Limits of the model.** The 26 mOhm is a 1 kHz AC impedance; the DC resistance that
governs sag and heat under a sustained load is higher, so these figures are a lower
bound. Real terminal voltage also depends on state of charge, temperature and pulse
length (diffusion effects). An equivalent-circuit model with RC branches captures
these; it is planned as a follow-up project. "Ideal runtime" ignores the capacity loss
at high C-rates and low temperature.

## 3. Wire gauge

American Wire Gauge diameters are defined by

```
d(n) = 0.127 mm * 92 ^ ((36 - n) / 39)
```

where gauges 1/0 to 4/0 are `n = 0 ... -3`. The conductor area is `A = pi * d^2 / 4`
and the copper resistance per metre at 20 degC is

```
R' = rho / A,   rho = 1.7241e-8 ohm*m (annealed copper, IACS)
```

For 10 AWG: `d = 2.588 mm`, `A = 5.26 mm2`, `R' = 3.28 mOhm/m`.

A wire is accepted when it passes two independent checks:

1. **Ampacity:** `A * J >= I_required`, where `J` is a design current density
   (default 8 A/mm2, a conservative value for short single silicone-insulated
   conductors in free air).
2. **Voltage drop:** `I * R' * 2L <= drop_limit * V_nom`, where `L` is the one-way
   length (the return conductor doubles the path).

The tool returns the thinnest gauge that passes both.

## 4. Fuse and wire coordination

The main fuse must not trip or age at full continuous current, so it is rated with a
margin (default 25 %) and rounded up to a standard size:

```
I_fuse = next standard rating >= 1.25 * I_continuous
```

The fuse exists to protect the wire, so the wire must be able to carry `I_fuse`
indefinitely. The ampacity check therefore uses `I_fuse`, while the voltage-drop
check uses the real operating current.

Example at 30 A: `1.25 x 30 = 37.5 A`, so a **40 A** fuse. The wire needs
`40 / 8 = 5 mm2`, so **10 AWG** (5.26 mm2, rated 42 A). Over 0.5 m one-way the drop is
`30 x 3.28e-3 x 1.0 = 0.098 V`, or 0.34 % of 28.8 V, and the wire dissipates
`30 x 0.098 = 2.95 W`.

## 5. Sizing algorithm (`packdesign design`)

For every cell in the library:

1. **Series count:** `S = round(V_target / V_cell,nom)`, or the fixed `S` given by the
   user. 36 V gives 10S for 3.6 V cells; 12.8 V gives 4S for 3.3 V LiFePO4 cells.
2. **Voltage limit:** reject the cell if `S * V_cell,max` exceeds the maximum allowed
   voltage.
3. **Parallel count:** the largest of all requirements:
   - energy: `ceil(E_target / (S * E_cell))`
   - capacity: `ceil(C_target / C_cell)`
   - discharge current: `ceil(I_target / I_cell,max)`
   - charge current: `ceil(I_charge / I_cell,chg)`

   The requirement that produced the largest value is reported as "Sized by".
4. **Mass limit:** reject the design if the cell mass exceeds the limit.

Feasible designs are ranked by cell mass (default), cell count or energy. Rejected
cells are listed with the reason, so the result is always explainable.

**Example.** 36 V, at least 500 Wh, 20 A continuous, with the Samsung 50E
(3.63 V, 4.9 Ah, 9.8 A):

- `S = round(36 / 3.63) = round(9.92) = 10`
- energy: `ceil(500 / (10 x 3.63 x 4.9)) = ceil(500 / 177.9) = ceil(2.81) = 3`
- current: `ceil(20 / 9.8) = ceil(2.04) = 3`
- result: **10S3P**, 30 cells, 533.6 Wh, 2.085 kg of cells
