
from flask import Flask, request, jsonify, make_response, render_template
import pandas as pd
import json
from flask_cors import CORS


app = Flask(__name__)
CORS(app)

# 데이터 로딩
# 내 파일이라 수정 필요
df = pd.read_csv('risk_result.csv', encoding='utf-8')  # 자치구별 노인친화 지표
#df = df.iloc[2:].reset_index(drop=True)  # 데이터 시작 행 정리
df["자치구"] = df["district"]  # 자치구 이름 정리


# 점수 계산 함수
def calculate_scores(weights,byNum ):
    features = list(weights.keys())
    weights_series = pd.Series(weights)


    # 선택한 지표만 추출
    df_selected = df[features]

    # 가중치 곱한 후 점수 계산
    df["score"] = df_selected.mul(weights_series).sum(axis=1)

    # 상위 3개 구 반환
    result = df[["자치구", "score"]].sort_values(by="score", ascending=False).head(byNum)
    return result.to_dict(orient="records")


@app.route("/")
def index():
    return render_template('index.html')

# API 라우팅
@app.route("/recommend")
def recommend():
    try:

        weights = {}
        num = 3

        for key in request.args:
            if key == "num":
                num = int(request.args[key])
            else:
                weights[key] = float(request.args.get(key))

        if not weights:
            return jsonify({"error": "가중치 데이터가 필요합니다."}), 400


        #weights = {'crime_rate':1}
        result = calculate_scores(weights, num)

        #response = make_response(jsonify({"result": result}))
        response = make_response(json.dumps({"result": result}, ensure_ascii=False))
        response.headers['Content-Type'] = 'application/json; charset=utf-8'

        return response

        #return jsonify({"result": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


if __name__ == "__main__":
    app.run(debug=True)
