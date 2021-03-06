import os
from datetime import datetime as dt
from datetime import timedelta
from pathlib import Path

import pandas as pd
from flask import Flask, request, jsonify
from flask_httpauth import HTTPBasicAuth
from werkzeug.security import generate_password_hash, check_password_hash
from flask_cors import CORS


def load_parquets(glob):
    return {
        f.stem.split("_")[0]: pd.read_parquet(f)
        for f in Path("data").glob(glob)
    }


def prep_historic(dfs, y_col):
    return {
        k: df.assign(x=lambda df: df.index.astype(str)).rename(columns={y_col: "y"})
        for k, df in dfs.items()
    }


def forecast2dict(dfs, reservoir, date):
    return [
        {"x": str(date + timedelta(days=int(kk.split(" ")[0])))[0:10], "y": vv}
        for ii, (kk, vv) in enumerate(dfs[reservoir].loc[date, :].to_dict().items())
    ]


def historic2dict(dfs, reservoir, date, history):
    return (
        dfs[reservoir]
        .fillna(0)
        .loc[
            (dfs[reservoir].index > (date - timedelta(days=history)))
            & (dfs[reservoir].index <= (date + timedelta(days=1))),
            ["x", "y"],
        ]
        .to_dict(orient="records")
    )


dfs_forecast = load_parquets("*_forecast.pq")
dfs_forecast_up = load_parquets("*_forecast_up.pq")
dfs_forecast_down = load_parquets("*_forecast_down.pq")
dfs_historic = load_parquets("*_historic.pq")

dfs_historic = prep_historic(dfs_historic, y_col="volume_bcm")
dfs_prec = prep_historic(dfs_historic, y_col="tp_0")

app = Flask(__name__)
auth = HTTPBasicAuth()
CORS(app)
users = {os.environ["USERNAME"]: generate_password_hash(os.environ["USERPASSWORD"])}


@auth.verify_password
def verify_password(username, password):
    if username in users and check_password_hash(users.get(username), password):
        return username


@app.route("/api/")
@auth.login_required
def index():
    reservoir = request.args.get("reservoir")
    history = int(request.args.get("history")) or 180
    date = request.args.get("date")

    if reservoir is None or reservoir not in dfs_historic.keys():
        return jsonify({"error": f"specify a reservoir from {dfs_historic.keys()}"})
    try:
        date = dt.strptime(date, "%Y-%m-%d")
    except Exception as e:
        return jsonify({"error": f"specify a date as YYYY-MM-DD: {e}"})

    try:
        return jsonify(
            {
                "forecast": forecast2dict(dfs_forecast, reservoir, date),
                "forecastUp": forecast2dict(dfs_forecast_up, reservoir, date),
                "forecastDown": forecast2dict(dfs_forecast_down, reservoir, date),
                "historic": historic2dict(dfs_historic, reservoir, date, history),
                "prec": historic2dict(dfs_prec, reservoir, date, history),
            }
        )
    except Exception as e:
        print("Error!", e)
        return jsonify({"Error": f"bad request: {e}"})


if __name__ == "__main__":
    app.run()
