import requests

def fetch_company_data(cin:str = None, company_name:str = None):
    url = "https://www.zaubacorp.com/typeahead"
    files = {
        'search': ('', '"U74899DL1988PTC032549"'),
        'filter': ('', '"company"'),
    }
    
    response = requests.post(url, files=files)

    if response.status_code == 200:
        return response.json()  # Assuming it returns JSON
    else:
        frappe.throw(f"Failed to fetch data: {response.status_code}")