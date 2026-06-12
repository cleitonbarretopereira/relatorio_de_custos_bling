import json
import requests
from requests.auth import HTTPBasicAuth
CREDENCIAIS = "tokens.json"
client_id = "f3a4678cb4556910a9289f756d6125cb79e61f2d"
client_secret = "2daa87c342dff8c7a6a3f77a3311b48f353d3e289cf8bf2b85fce807d7f2"  
authorization_code = "ee3df0decd19d2b0616a678ec1fd84447c7ff880"

url = "https://api.bling.com.br/Api/v3/oauth/token"

data = {
    "grant_type": "authorization_code",
    "code": authorization_code,
    "redirect_uri": "http://localhost"
}

print("🔄 Enviando requisição para obter o token...")

response = requests.post(
    url, 
    auth=HTTPBasicAuth(client_id, client_secret), 
    data=data
)

print("Status Code:", response.status_code)

if response.status_code == 200:
    token_info = response.json()
    print("\n✅ Sucesso!")
    print("Access Token:", token_info.get("access_token"))
    print("Refresh Token:", token_info.get("refresh_token"))
    print("Expires in:", token_info.get("expires_in"))
    
    with open(CREDENCIAIS, "w") as f:
        json.dump(token_info, f, indent=4)

    print("**\n💾 Token salvo!**")
    
else:
    print("**\n❌ Erro ao obter token:**")
    print(response.text)