from app.main import STANDARD_WARNING, parse_fields, verify


def test_parse_fields():
    text = f'''Brand: OLD TOM DISTILLERY
Class/Type: Kentucky Straight Bourbon Whiskey
Alcohol Content: 45%
Net Contents: 750 mL
Producer: Old Tom Distillery
Country of Origin: United States
{STANDARD_WARNING}'''
    result = parse_fields(text)
    assert result['brand_name'] == 'OLD TOM DISTILLERY'
    assert result['alcohol_content'] == '45%'
    assert result['net_contents'] == '750 mL'
    assert 'GOVERNMENT WARNING' in result['government_warning']


def test_pass():
    app = {'brand_name':'OLD TOM DISTILLERY','class_type':'Kentucky Straight Bourbon Whiskey','alcohol_content':'45%','net_contents':'750 mL','producer':'Old Tom Distillery','country_of_origin':'United States'}
    text = f'''Brand: OLD TOM DISTILLERY
Class/Type: Kentucky Straight Bourbon Whiskey
Alcohol Content: 45%
Net Contents: 750 mL
Producer: Old Tom Distillery
Country of Origin: United States
{STANDARD_WARNING}'''
    result = verify(app, parse_fields(text), text, .9)
    assert result['status'] == 'PASS'


def test_warning_failure():
    app = {'brand_name':'OLD TOM DISTILLERY','class_type':'Kentucky Straight Bourbon Whiskey','alcohol_content':'45%','net_contents':'750 mL','producer':'Old Tom Distillery','country_of_origin':'United States'}
    text = '''Brand: OLD TOM DISTILLERY
Class/Type: Kentucky Straight Bourbon Whiskey
Alcohol Content: 45%
Net Contents: 750 mL
Producer: Old Tom Distillery
Country of Origin: United States
GOVERNMENT WARNING: Different warning'''
    result = verify(app, parse_fields(text), text, .9)
    assert result['status'] == 'FAIL'


def test_ocr_ambiguity_routes_to_review():
    app = {'brand_name':'OLD TOM DISTILLERY','class_type':'Kentucky Straight Bourbon Whiskey','alcohol_content':'45%','net_contents':'750 mL','producer':'Old Tom Distillery','country_of_origin':'United States'}
    noisy_warning = STANDARD_WARNING.replace('should not', 'shouLd not').replace('machinery', 'machinerv')
    extracted = {
        'brand_name':'',
        'class_type':'Kentucky Straight Bourbon Whiskey',
        'alcohol_content':'45%',
        'net_contents':'750 mL',
        'producer':'OLp TOM DISTILLERY',
        'country_of_origin':'United States',
        'government_warning': noisy_warning,
    }
    result = verify(app, extracted, noisy_warning, .92)
    assert result['status'] == 'NEEDS REVIEW'
    assert any(c['status'] == 'review' for c in result['checks'])


def test_numeric_mismatch_remains_hard_fail():
    app = {'brand_name':'OLD TOM DISTILLERY','class_type':'Kentucky Straight Bourbon Whiskey','alcohol_content':'45%','net_contents':'750 mL','producer':'Old Tom Distillery','country_of_origin':'United States'}
    text = f'''Brand: OLD TOM DISTILLERY
Class/Type: Kentucky Straight Bourbon Whiskey
Alcohol Content: 40%
Net Contents: 750 mL
Producer: Old Tom Distillery
Country of Origin: United States
{STANDARD_WARNING}'''
    result = verify(app, parse_fields(text), text, .9)
    assert result['status'] == 'FAIL'


def test_implausible_abv_routes_to_review():
    app = {'brand_name':'WOODFORD RESERVE','class_type':'Kentucky Straight Bourbon Whiskey','alcohol_content':'45.2%','net_contents':'750 mL','producer':'Woodford Reserve Distillery','country_of_origin':'United States'}
    extracted = {'brand_name':'WOODFORD RESERVE','class_type':'Kentucky Straight Bourbon Whiskey','alcohol_content':'459%','net_contents':'750 mL','producer':'Woodford Reserve Distillery','country_of_origin':'United States','government_warning':STANDARD_WARNING}
    result = verify(app, extracted, '', .9)
    assert result['status'] == 'NEEDS REVIEW'
    abv = next(c for c in result['checks'] if c['field'] == 'Alcohol Content')
    assert abv['status'] == 'review'


def test_multi_panel_aggregation_combines_evidence():
    from app.main import aggregate_panel_results
    app = {'brand_name':'OLD TOM DISTILLERY','class_type':'Kentucky Straight Bourbon Whiskey','alcohol_content':'45%','net_contents':'750 mL','producer':'Old Tom Distillery','country_of_origin':'United States'}
    front = {'filename':'front.jpg','ocr_confidence':.92,'raw_text':'front','extracted':{'brand_name':'OLD TOM DISTILLERY','class_type':'Kentucky Straight Bourbon Whiskey','alcohol_content':'45%','net_contents':'750 mL','producer':'','country_of_origin':'','government_warning':''}}
    back = {'filename':'back.jpg','ocr_confidence':.90,'raw_text':'back','extracted':{'brand_name':'','class_type':'','alcohol_content':'','net_contents':'','producer':'Old Tom Distillery','country_of_origin':'United States','government_warning':STANDARD_WARNING}}
    result = aggregate_panel_results(app, [front, back])
    assert result['status'] == 'PASS'
    assert result['provenance']['alcohol_content'] == 'front.jpg'
    assert result['provenance']['government_warning'] == 'back.jpg'


def test_low_confidence_plausible_abv_mismatch_routes_to_review():
    app = {'brand_name':'WOODFORD RESERVE','class_type':'Kentucky Straight Bourbon Whiskey','alcohol_content':'45.2%','net_contents':'750 mL','producer':'Woodford Reserve Distillery','country_of_origin':'United States'}
    extracted = {'brand_name':'','class_type':'Kentucky Straight Bourbon Whiskey','alcohol_content':'69%','net_contents':'','producer':'Woodford Reserve Distillery','country_of_origin':'','government_warning':STANDARD_WARNING}
    result = verify(app, extracted, '', .77)
    assert result['status'] == 'NEEDS REVIEW'
    abv = next(c for c in result['checks'] if c['field'] == 'Alcohol Content')
    assert abv['status'] == 'review'
    assert 'could not be reliably verified' in abv['detail']

def test_high_confidence_plausible_abv_mismatch_still_fails():
    app = {'brand_name':'OLD TOM DISTILLERY','class_type':'Kentucky Straight Bourbon Whiskey','alcohol_content':'45%','net_contents':'750 mL','producer':'Old Tom Distillery','country_of_origin':'United States'}
    extracted = {'brand_name':'OLD TOM DISTILLERY','class_type':'Kentucky Straight Bourbon Whiskey','alcohol_content':'40%','net_contents':'750 mL','producer':'Old Tom Distillery','country_of_origin':'United States','government_warning':STANDARD_WARNING}
    result = verify(app, extracted, '', .94)
    assert result['status'] == 'FAIL'


def test_low_confidence_material_warning_difference_routes_to_review():
    app = {'brand_name':'ABC','class_type':'STRAIGHT RYE WHISKY','alcohol_content':'45%','net_contents':'750 mL','producer':'ABC DISTILLERY','country_of_origin':'United States'}
    extracted = {'brand_name':'','class_type':'','alcohol_content':'45%','net_contents':'750 mL','producer':'','country_of_origin':'','government_warning':'GOVERNMENT WARNING: badly corrupted OCR text that does not reliably preserve the statutory warning'}
    result = verify(app, extracted, '', .65)
    assert result['status'] == 'NEEDS REVIEW'
    warning = next(c for c in result['checks'] if c['field'] == 'Government Warning')
    assert warning['status'] == 'review'

def test_high_confidence_material_warning_difference_still_fails():
    app = {'brand_name':'OLD TOM DISTILLERY','class_type':'Kentucky Straight Bourbon Whiskey','alcohol_content':'45%','net_contents':'750 mL','producer':'Old Tom Distillery','country_of_origin':'United States'}
    extracted = {'brand_name':'OLD TOM DISTILLERY','class_type':'Kentucky Straight Bourbon Whiskey','alcohol_content':'45%','net_contents':'750 mL','producer':'Old Tom Distillery','country_of_origin':'United States','government_warning':'GOVERNMENT WARNING: Different warning'}
    result = verify(app, extracted, '', .95)
    assert result['status'] == 'FAIL'
    warning = next(c for c in result['checks'] if c['field'] == 'Government Warning')
    assert warning['status'] == 'fail'


def test_parse_producer_address():
    text = """Producer: ABC DISTILLERY
Address: Frederick, MD
Alcohol Content: 45%
Net Contents: 750 mL"""
    result = parse_fields(text)
    assert result['producer_address'] == 'Frederick, MD'


def test_blank_optional_fields_do_not_block_pass():
    app = {'brand_name':'OLD TOM DISTILLERY','class_type':'Kentucky Straight Bourbon Whiskey','alcohol_content':'45%','net_contents':'750 mL','producer':'Old Tom Distillery','producer_address':'','country_of_origin':''}
    extracted = {'brand_name':'OLD TOM DISTILLERY','class_type':'Kentucky Straight Bourbon Whiskey','alcohol_content':'45%','net_contents':'750 mL','producer':'Old Tom Distillery','producer_address':'','country_of_origin':'','government_warning':STANDARD_WARNING}
    result = verify(app, extracted, '', .95)
    assert result['status'] == 'PASS'
