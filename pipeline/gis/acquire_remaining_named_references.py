"""Bounded source windows for finite interior/harbour/art massing tasks."""
import sys
from pathlib import Path
import extract_named_feature_crops as extractor

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'pipeline/routes'))
from orthophoto_reference import build

CROPS=[
    ('north-sculptures',(1222.,5.),60,'490000_5461000'),
    ('totem-sculptures',(1610.,-390.),85,'491000_5460000'),
    ('harry-jerome',(1744.48,-485.37),20,'491000_5460000'),
]


def main():
    extractor.FEATURES=CROPS;extractor.main()
    for name,xy,span,pixel in [
        ('named-north-sculptures',(1225.,5.),130,.075),
        ('named-totem-sculptures',(1610.,-390.),180,.1),
        ('named-harry-jerome',(1744.48,-485.37),45,.075),
        ('named-train-buildings',(690.,-70.),240,.18),
        ('named-deadman-buildings',(1460.,-810.),250,.18),
    ]:
        if not (ROOT/f'evidence/corridor/ortho-utm/{name}.png').exists():build(name,*xy,span,pixel)


if __name__=='__main__':main()
