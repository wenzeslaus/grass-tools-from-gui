## DESCRIPTION

*m.measure* provides the user with a way to measure the lengths and
areas of lines and polygons. Areas can be stated in acres, hectares,
square miles, square feet, square meters and square kilometers.

For each segment between two consecutive coordinate pairs, the tool
also reports the bearing of the segment in degrees clockwise from
grid north (0-360). The bearing is planar (a grid bearing computed
from the coordinate differences), even in a latitude-longitude
coordinate reference system where lengths are computed geodesically.
In latitude-longitude, the reported bearing is therefore not a
geodesic azimuth.

## EXAMPLES

Distance example in a latitude-longitude coordinate reference system (on
great circle, i.e. an orthodrome):

```sh
Bonn_DE="7.09549,50.73438"
Philadelphia_US="-75.16379,39.95233"

m.measure coordinates="$Bonn_DE,$Philadelphia_US" units=kilometers
Length:  6217.916452 kilometers
Bearing: 262.532585 degrees
```

Note that the bearing is planar (computed from the longitude and
latitude differences), not a geodesic azimuth.

![Visualization (with d.geodesic) of m.measure distance example](m_measure_distance.png)  
*Visualization (with d.geodesic) of m.measure
distance example*

As an example for the North Carolina sample dataset, here four points
describing a square of 1000m side length:

```sh
m.measure units=meters \
  coordinates=922000,2106000,923000,2106000,923000,2107000,922000,2107000
Length:  3000.000000 meters
Bearing:  90.000000 degrees
Bearing:   0.000000 degrees
Bearing: 270.000000 degrees
Area:    1000000.000000 square meters

# script style output:
m.measure -g units=hectares \
  coordinates=922000,2106000,923000,2106000,923000,2107000,922000,2107000
units=meters,hectares
length=3000.000000
bearing=90.000000,0.000000,270.000000
area=100.000000
```

Measuring length and area using Python (JSON output):

```python
import grass.script as gs

data = gs.parse_command(
    "m.measure",
    coordinates=[
        "922000",
        "2106000",
        "923000",
        "2106000",
        "923000",
        "2107000",
        "922000",
        "2107000",
    ],
    format="json",
)
print(data)
```

Possible output:

```text
{'units': {'length': 'meters', 'area': 'square meters', 'bearing': 'degrees'}, 'length': 3000, 'bearings': [90, 0, 270], 'area': 1000000}
```

## SEE ALSO

*[d.geodesic](d.geodesic.md)*

## AUTHORS

Glynn Clements  
Some updates by Martin Landa, CTU in Prague, Czech Republic  
  
Derived from d.measure by James Westervelt, Michael Shapiro, U.S. Army
Construction Engineering Research Laboratory
