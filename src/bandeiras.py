# Mapeamento de nome de seleção (em inglês, do results.csv) para seu emoji de bandeira
DICIONARIO_BANDEIRAS = {
    # Seleções da Copa 2026
    "Mexico": "🇲🇽",
    "South Africa": "🇿🇦",
    "South Korea": "🇰🇷",
    "Czech Republic": "🇨🇿",
    "Canada": "🇨🇦",
    "Bosnia and Herzegovina": "🇧🇦",
    "Qatar": "🇶🇦",
    "Switzerland": "🇨🇭",
    "Brazil": "🇧🇷",
    "Morocco": "🇲🇦",
    "Haiti": "🇭🇹",
    "Scotland": "🏴󠁧󠁢󠁳󠁣󠁴󠁿",
    "United States": "🇺🇸",
    "Paraguay": "🇵🇾",
    "Australia": "🇦🇺",
    "Turkey": "🇹🇷",
    "Germany": "🇩🇪",
    "Curaçao": "🇨🇼",
    "Ivory Coast": "🇨🇮",
    "Ecuador": "🇪🇨",
    "Netherlands": "🇳🇱",
    "Japan": "🇯🇵",
    "Sweden": "🇸🇪",
    "Tunisia": "🇹🇳",
    "Belgium": "🇧🇪",
    "Egypt": "🇪🇬",
    "Iran": "🇮🇷",
    "New Zealand": "🇳🇿",
    "Spain": "🇪🇸",
    "Cape Verde": "🇨🇻",
    "Saudi Arabia": "🇸🇦",
    "Uruguay": "🇺🇾",
    "France": "🇫🇷",
    "Senegal": "🇸🇳",
    "Iraq": "🇮🇶",
    "Norway": "🇳🇴",
    "Argentina": "🇦🇷",
    "Algeria": "🇩🇿",
    "Austria": "🇦🇹",
    "Jordan": "🇯🇴",
    "Portugal": "🇵🇹",
    "DR Congo": "🇨🇩",
    "Uzbekistan": "🇺🇿",
    "Colombia": "🇨🇴",
    "England": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "Croatia": "🇭🇷",
    "Ghana": "🇬🇭",
    "Panama": "🇵🇦",
    
    # Outras seleções comuns para fallback histórico
    "Wales": "🏴󠁧󠁢󠁷󠁬󠁳󠁿",
    "Italy": "🇮🇹",
    "Chile": "🇨🇱",
    "Peru": "🇵🇪",
    "Venezuela": "🇻🇪",
    "Bolivia": "🇧🇴",
    "Costa Rica": "🇨🇷",
    "Jamaica": "🇯🇲",
    "Honduras": "🇭🇳",
    "El Salvador": "🇸🇻",
    "Nigeria": "🇳🇬",
    "Cameroon": "🇨🇲",
    "Greece": "🇬🇷",
    "Denmark": "🇩🇰",
    "Ukraine": "🇺🇦",
    "Poland": "🇵🇱",
    "Russia": "🇷🇺",
    "China PR": "🇨🇳",
    "Iceland": "🇮🇸"
}

def obter_bandeira(nome):
    """
    Retorna apenas o emoji da bandeira para a seleção informada.
    """
    if not nome:
        return "🏳️"
    return DICIONARIO_BANDEIRAS.get(nome.strip(), "🏳️")

def com_bandeira(nome):
    """
    Retorna o emoji da bandeira concatenado com o nome da seleção.
    """
    if not nome:
        return ""
    bandeira = obter_bandeira(nome)
    return f"{bandeira} {nome}"
