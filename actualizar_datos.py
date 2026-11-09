"""Actualiza precios de acciones colombianas para el proyecto UNIPAZ.
Ejecutar en Python 3.12 con yfinance y pandas.
"""
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

ACCIONES = [
    ("ECOPETROL.CL", "Ecopetrol", "ECOPETROL", "Petróleo y gas"),
    ("PFCIBEST.CL", "Grupo Cibest, preferencial", "PFCIBEST", "Financiero"),
    ("CIBEST.CL", "Grupo Cibest, ordinaria", "CIBEST", "Financiero"),
    ("ISA.CL", "ISA", "ISA", "Energía e infraestructura"),
    ("EXITO.CL", "Grupo Éxito", "EXITO", "Comercio"),
    ("PFAVAL.CL", "Grupo Aval, preferencial", "PFAVAL", "Financiero"),
    ("CELSIA.CL", "Celsia", "CELSIA", "Energía"),
    ("GEB.CL", "Grupo Energía Bogotá", "GEB", "Energía"),
]
SALIDA = Path(__file__).resolve().parent / "datos.json"
FUENTE = "Yahoo Finance (yfinance); rentabilidades con precio ajustado por dividendos"


def numero(x):
    """Redondea números finitos para JSON; conserva null cuando falta un dato."""
    try:
        n = float(x)
        return round(n, 2) if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def obtener_accion(yf, pd, np, item):
    ticker, nombre, nemotecnico, sector = item
    hist = yf.Ticker(ticker).history(period="3y", auto_adjust=False)
    if hist is None or hist.empty or "Close" not in hist or "Adj Close" not in hist:
        raise ValueError("No se obtuvieron precios Close y Adj Close")
    hist = hist.sort_index().dropna(subset=["Close", "Adj Close"])
    hist = hist[(hist["Close"] > 0) & (hist["Adj Close"] > 0)]
    if len(hist) < 2:
        raise ValueError("Historial insuficiente")
    close = hist["Close"].astype(float)
    adj = hist["Adj Close"].astype(float)
    ultimo = hist.index[-1]
    precio = float(close.iloc[-1])
    umbral = ultimo - pd.DateOffset(years=1)
    antiguedad = (ultimo - hist.index[0]).days

    # Rentabilidades: precios ajustados por dividendos; riesgo: último año.
    if antiguedad >= 360:
        idx = min(range(len(hist)), key=lambda k: abs((hist.index[k] - umbral).days))
        rent_1a = (adj.iloc[-1] / adj.iloc[idx] - 1) * 100
    else:
        rent_1a = None
    anos = (ultimo - hist.index[0]).total_seconds() / (365.2425 * 86400)
    rent_3a = ((adj.iloc[-1] / adj.iloc[0]) ** (1 / anos) - 1) * 100 if anos > 0 else None
    ult_ano = hist.loc[hist.index >= umbral]
    adj_ano = ult_ano["Adj Close"].astype(float)
    rend_log = np.log(adj_ano / adj_ano.shift(1)).dropna()
    volatilidad = (rend_log.std(ddof=1) * np.sqrt(252) * 100) if len(rend_log) >= 3 else None
    caida = (adj_ano / adj_ano.cummax() - 1).min() * 100 if not adj_ano.empty else None
    dividendos = hist["Dividends"] if "Dividends" in hist else pd.Series(0, index=hist.index)
    d_ano = dividendos.loc[hist.index >= ultimo - pd.Timedelta(days=365)].fillna(0).sum()
    mensual = close.resample("ME").last().dropna()
    historico = [{"mes": mes.strftime("%Y-%m"), "cierre": numero(v)} for mes, v in mensual.items()]
    return {
        "ticker": ticker,
        "nombre": nombre,
        "nemotecnico": nemotecnico,
        "sector": sector,
        "moneda": "COP",
        "precio": numero(precio),
        "fecha": ultimo.date().isoformat(),
        "variacion_dia_pct": numero((close.iloc[-1] / close.iloc[-2] - 1) * 100),
        "rent_1a_pct": numero(rent_1a),
        "rent_anual_3a_pct": numero(rent_3a),
        "volatilidad_anual_pct": numero(volatilidad),
        "caida_maxima_1a_pct": numero(caida),
        "dividendo_rend_pct": numero(d_ano / precio * 100),
        "historico": historico,
    }


def obtener_trm(yf):
    try:
        hist = yf.Ticker("USDCOP=X").history(period="5d", auto_adjust=False)
        if hist is None or hist.empty:
            return None
        cierre = hist["Close"].dropna()
        if cierre.empty:
            return None
        return {"valor": numero(cierre.iloc[-1]), "fecha": cierre.index[-1].date().isoformat()}
    except Exception as exc:
        print(f"No se pudo obtener TRM: {exc}")
        return None


def ejecutar():
    try:
        import numpy as np
        import pandas as pd
        import yfinance as yf
    except Exception as exc:
        print(f"Faltan librerías: {exc}. Se conserva datos.json anterior.")
        return
    acciones, errores = [], []
    for item in ACCIONES:
        try:
            accion = obtener_accion(yf, pd, np, item)
            acciones.append(accion)
            print(f"OK {item[0]}: {accion['fecha']}")
        except Exception as exc:
            errores.append({"ticker": item[0], "motivo": str(exc)[:250]})
            print(f"ERROR {item[0]}: {exc}")
    print(f"Resumen: {len(acciones)} de {len(ACCIONES)} acciones actualizadas.")
    for err in errores:
        print(f"  Falló {err['ticker']}: {err['motivo']}")
    if not acciones:
        print("No hubo datos válidos; se conserva el datos.json anterior.")
        return
    datos = {
        "actualizado": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fuente": FUENTE,
        "trm": obtener_trm(yf),
        "acciones": acciones,
        "errores": errores,
    }
    temporal = SALIDA.with_suffix(".json.tmp")
    try:
        temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporal, SALIDA)
        print(f"Archivo actualizado: {SALIDA}")
    except Exception as exc:
        print(f"No se pudo escribir datos.json: {exc}")
        try:
            temporal.unlink(missing_ok=True)
        except Exception:
            pass


if __name__ == "__main__":
    try:
        ejecutar()
    except Exception as exc:
        print(f"Error inesperado: {exc}; se conserva datos.json anterior.")
