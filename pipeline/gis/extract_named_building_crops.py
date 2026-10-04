"""Extra raw returns for pool and marina forms omitted by LAS roof classes."""
import extract_named_feature_crops as extractor

extractor.FEATURES=[
    ('yacht-full-west',(1180,-850),330,'490000_5460000'),
    ('yacht-port-west',(1240,-790),250,'490000_5460000'),
    ('yacht-port-east',(1240,-790),250,'491000_5460000'),
    ('second-pool',(-620,-810),85,'489000_5460000'),
    ('second-pool-west',(-620,-810),85,'488000_5460000'),
]

if __name__=='__main__':extractor.main()
