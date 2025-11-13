### import pandas as pd
### import numpy as np
### from sklearn.model_selection import train_test_split
### from sklearn.ensemble import RandomForestClassifier
### from sklearn.feature_extraction.text import TfidfVectorizer
### from sklearn.preprocessing import OneHotEncoder
### from sklearn.compose import ColumnTransformer
### from sklearn.pipeline import Pipeline
### from sklearn.metrics import classification_report, accuracy_score
### import matplotlib.pyplot as plt
### import seaborn as sns
### import joblib
### from tqdm import tqdm
### import warnings
### import re
### import string
### from sklearn.feature_extraction import text
### stop_words = text.ENGLISH_STOP_WORDS
### import nltk

import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report

import pandas as pd
df = pd.read_csv("simap_last10d_sample.csv")

#df = pd.read_csv(r"C:\Users\Akishan\Documents\FHNW BAI\3. Semester\ML\MLOps-HS-25\data\raw\simap_last10d_sample.csv")


print(df.shape)
print(df.head())


df["text_attribute"] = df["title"] + " " + df["description"]
df["text_attribute"] = df["text_attribute"].str.lower()


df = df.dropna(subset=["order_type"])
df = df[df["order_type"] != "unknown"]

#zweiti zielvariable: project_value_chf
import numpy as np
import re

def parse_value(x):
    if pd.isna(x):
        return np.nan
    s = str(x)
    s = s.replace("CHF", "").replace("’", "").replace("'", "").replace(" ", "")
    s = re.sub(r"[^0-9.]", "", s)
    try:
        return float(s)
    except:
        return np.nan


df["value_raw"] = df["estimated_value"].fillna(df["award_value"])
df["project_value_chf"] = df["value_raw"].apply(parse_value)


q1, q2 = df["project_value_chf"].quantile([0.45, 0.70])
def size_class(v):
    if np.isnan(v):
        return "unknown"
    if v <= q1:
        return "klein"
    if v <= q2:
        return "mittel"
    return "gross"

df["size_bucket"] = df["project_value_chf"].apply(size_class)
print(df["size_bucket"].value_counts())


y = df["order_type"]
x = df[["text_attribute", "country", "canton", "process_type", "project_type"]].fillna("")



from sklearn.model_selection import train_test_split


X_train, X_test, y_train, y_test = train_test_split(x, y, test_size=0.15, random_state=42,stratify=y)


from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import OneHotEncoder
from sklearn.compose import ColumnTransformer

# Wenn zu recheintensiv > max_features abesetze
preprocessor = ColumnTransformer(
    transformers=[
        ("text", TfidfVectorizer(max_features=15000), "text_attribute"),
        ("cat", OneHotEncoder(handle_unknown="ignore"), ["country", "canton", "process_type", "project_type"]),
    ], remainder="drop"
)

from sklearn.ensemble import RandomForestClassifier

# Wenn zu lang dured > n_estimators abesetze
model = RandomForestClassifier(n_estimators=666, random_state=42)


from sklearn.pipeline import Pipeline

#Zum zemmefüehre vo td idf, onehot und random forest
klassifikator = Pipeline(steps=[("preprocessor", preprocessor), ("classifier", model)])

klassifikator.fit(X_train, y_train)
  

#Uswertig vo de Performance
from sklearn.metrics import classification_report

y_pred = klassifikator.predict(X_test)
print(classification_report(y_test, y_pred))

df_size = df[df["size_bucket"] != "unknown"]


X2 = df_size[["text_attribute", "country", "canton", "process_type", "project_type"]].fillna("")
y2 = df_size["size_bucket"]


X2_train, X2_test, y2_train, y2_test = train_test_split(
    X2, y2, test_size=0.15, random_state=42, stratify=y2
)


preprocessor2 = ColumnTransformer(
    transformers=[
        ("text", TfidfVectorizer(max_features=15000), "text_attribute"),
        ("cat", OneHotEncoder(handle_unknown="ignore"), ["country", "canton", "process_type", "project_type"]),
    ],
    remainder="drop"
)


model2 = RandomForestClassifier(n_estimators=666, random_state=42)


size_classifier = Pipeline(steps=[
    ("preprocessor", preprocessor2),
    ("classifier", model2)
])


size_classifier.fit(X2_train, y2_train)


y2_pred = size_classifier.predict(X2_test)
print("\n\n--- Klassifikationsreport für Projektgröße (size_bucket) ---")
print(classification_report(y2_test, y2_pred))


def predict_project_info(df_input):

    order_type_pred = klassifikator.predict(df_input)
    size_bucket_pred = size_classifier.predict(df_input)
    result = pd.DataFrame({"order_type_pred": order_type_pred, "size_bucket_pred": size_bucket_pred})

    return result