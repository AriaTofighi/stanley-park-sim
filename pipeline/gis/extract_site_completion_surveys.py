"""Finite raw-return crops for the named public-space completion package."""
import extract_named_feature_crops as source

source.FEATURES=[
    ('devonian-pond',(560,-880),62,'490000_5460000'),
    ('salmon-lower-pool',(860,-455),45,'490000_5460000'),
    ('port-view',(1932,-258),28,'491000_5460000'),
]

if __name__=='__main__':source.main()
