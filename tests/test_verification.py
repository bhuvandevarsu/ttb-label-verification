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
