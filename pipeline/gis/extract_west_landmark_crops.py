"""Reproduce the small west-landmark raw crops without shared pipeline edits."""
import extract_named_feature_crops as extractor

extractor.FEATURES=[
    ('hollow-tree',(-765.57,485.71),25,'488000_5461000'),
    ('siwash-lookout',(-923.12,655.90),22,'488000_5461000'),
    ('third-beach',(-921.57,57.77),50,'488000_5461000'),
]

if __name__=='__main__':extractor.main()
