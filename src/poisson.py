import numpy as np
from scipy.stats import poisson

def calcular_probabilidades_resultado(lambda_casa, lambda_visit, max_gols=10):
    """
    Calcula as probabilidades de vitória (time de casa), empate e derrota (time visitante)
    a partir dos gols esperados (lambdas) usando distribuições Poisson independentes.
    Retorna (prob_vitoria, prob_empate, prob_derrota).
    """
    # Garantir que lambdas sejam float positivos válidos
    lambda_casa = max(float(lambda_casa), 1e-8)
    lambda_visit = max(float(lambda_visit), 1e-8)
    
    # Gerar grade de gols de 0 até max_gols
    gols = np.arange(max_gols + 1)
    
    # Probabilidades individuais (truncadas e normalizadas)
    prob_casa = poisson.pmf(gols, lambda_casa)
    prob_casa /= prob_casa.sum()
    
    # Probabilidades do visitante
    prob_visit = poisson.pmf(gols, lambda_visit)
    prob_visit /= prob_visit.sum()
    
    # Obter a matriz de probabilidade conjunta
    matriz_conjunta = np.outer(prob_casa, prob_visit)
    
    # Vitória (casa): soma abaixo da diagonal principal (gols_casa > gols_visitante)
    prob_vitoria = np.sum(np.tril(matriz_conjunta, -1))
    
    # Empate: soma da diagonal principal (gols_casa == gols_visitante)
    prob_empate = np.sum(np.diag(matriz_conjunta))
    
    # Derrota (visitante): soma acima da diagonal principal (gols_casa < gols_visitante)
    prob_derrota = np.sum(np.triu(matriz_conjunta, 1))
    
    return float(prob_vitoria), float(prob_empate), float(prob_derrota)

def obter_resultado_real(gols_casa, gols_visitante):
    """
    Retorna a representação em string ('V', 'E', 'D') do resultado real do jogo.
    """
    if gols_casa > gols_visitante:
        return 'V'
    elif gols_casa == gols_visitante:
        return 'E'
    else:
        return 'D'
