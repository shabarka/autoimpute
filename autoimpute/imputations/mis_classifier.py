"""Class to predict missingness in a dataset and generate test cases.

The main class in this module is the MissingnessClassifier. It has numerous
use cases. First, it fits the columns of a DataFrame and predicts whether
or not a given observation is missing or not, based on all available
information in other columns (todo: allow for flexible column specification).
Second, it allows users to generate test cases for imputation analysis. Test
cases are values that are truly observed but have a high probability of being
missing. These cases make the imputation process supervised as opposed to
unsupervised. A user never knows the true value of missing data, but a user
can verify imputation methods on test cases for which the true value is known.
More information regarding each feature is available in the docstrings of
instance methods within the MissingnessClassifier.

Todo:
    * Allow for flexible column specification used in predictor.
    * Update docstrings for class initialization and instance methods.
    * Add examples of proper usage for the class and its instance methods.
"""

import warnings
import numpy as np
import pandas as pd
from xgboost import XGBClassifier
from sklearn.base import clone, BaseEstimator, ClassifierMixin
from sklearn.utils.validation import check_is_fitted
from autoimpute.utils.checks import check_missingness
from autoimpute.utils.helpers import _nan_col_dropper
# pylint:disable=attribute-defined-outside-init
# pylint:disable=arguments-differ

class MissingnessClassifier(BaseEstimator, ClassifierMixin):
    """
    Predicts the likelihood of missingness for a given dataset
    Default method uses xgboost, although other predictors are supported
    """
    def __init__(self, classifier=None, scaler=None, verbose=False):
        """Create an instance of the MissingnessPredictor"""
        self.classifier = classifier
        self.scaler = scaler
        self.verbose = verbose

    @property
    def classifier(self):
        """return the classifier property"""
        return self._classifier

    @property
    def scaler(self):
        """return the scaler property"""
        return self._scaler

    @classifier.setter
    def classifier(self, c):
        """Validate the classifier property and set default param"""
        if c is None:
            self._classifier = XGBClassifier()
        else:
            m = "predict_proba"
            if not hasattr(c, m):
                raise ValueError(f"Classifier must implement {m} method.")
            else:
                self._classifier = c

    @scaler.setter
    def scaler(self, s):
        """Validate the scaler property and confirm default param"""
        if s is None:
            self._scaler = s
        else:
            m = "fit_transform"
            if not hasattr(s, m):
                raise ValueError(f"Scaler must implement {m} method.")
            else:
                self._scaler = s

    def _check_if_single_dummy(self, X):
        """Detect if single category present for a one-hot enocded feature"""
        cats = X.columns.tolist()
        if len(cats) == 1:
            c = cats[0]
            cf = c.split('_')[0]
            msg = f"{c} only category for feature {cf}."
            cons = f"Consider removing {cf} from dataset."
            warnings.warn(f"{msg} {cons}")

    def _scaler_fit(self):
        """Method to scale data based on scaler provided"""
        # if scaler used, must be from sklearn library
        if self._len_num > 0:
            sc = clone(self.scaler)
            self._scaled_num = sc.fit(self._data_num.values)
        if self._len_dum > 0:
            sc = clone(self.scaler)
            self._scaled_dum = sc.fit(self._data_dum.values)

    def _scaler_transform(self):
        """Method to transform data using scaled fit"""
        if not self._scaled_num is None:
            cn = self._data_num.columns.tolist()
            sn = self._scaled_num.transform(self._data_num.values)
            self._data_num = pd.DataFrame(sn, columns=cn)
        if not self._scaled_dum is None:
            cd = self._data_dum.columns.tolist()
            sd = self._scaled_dum.transform(self._data_dum.values)
            self._data_dum = pd.DataFrame(sd, columns=cd)

    def _prep_dataframes(self, X):
        """Prepare numeric and categorical data for fit method"""
        X, self._nc = _nan_col_dropper(X)
        self.data_mi = pd.isnull(X)*1
        self._data_num = X.select_dtypes(include=(np.number,))
        self._len_num = len(self._data_num.columns)

        # right now, only support for one-hot encoding
        dummies = [pd.get_dummies(X[col], prefix=col)
                   for col in X.select_dtypes(include=(np.object,))]
        ld = len(dummies)
        if ld == 0:
            self._data_dum = pd.DataFrame()
        elif ld == 1:
            self._data_dum = dummies[0]
            self._check_if_single_dummy(self._data_dum)
        else:
            self._data_dum = pd.concat(dummies, axis=1)
            for each_dum in dummies:
                self._check_if_single_dummy(each_dum)
        self._len_dum = len(self._data_dum.columns)

        # print categorical and numeric columns if verbose true
        if self.verbose:
            print(f"Number of numeric columns: {self._len_num}")
            print(f"Number of categorical columns: {self._len_dum}")

    def _prep_classifier_cols(self, X, i, c):
        """perpare the data for each classifier"""
        # dealing with a numeric column...
        if X[c].dtype == np.number:
            if self._len_num > 1:
                num_cols = self._data_num.drop(c, axis=1)
                num_str = num_cols.columns.tolist()
                if self._len_dum > 0:
                    dummy_str = self._data_dum.columns.tolist()
                    cl = [num_cols.values, self._data_dum.values]
                    x = np.concatenate(cl, axis=1)
                else:
                    dummy_str = None
                    x = num_cols.values
            else:
                num_str = None
                if self._len_dum > 0:
                    dummy_str = self._data_dum.columns.tolist()
                    x = self._data_dum.values
                else:
                    raise ValueError("Need at least one predictor column.")
            if self.verbose:
                print(f"Columns used for {i} - {c}:")
                print(f"Numeric: {num_str}")
                print(f"Categorical: {dummy_str}")

        # dealing with categorical columns...
        else:
            d = [k for k in self._data_dum.columns
                 if not k.startswith(f"{c}_")]
            len_d = len(d)
            if len_d > 0:
                dummy_cols = self._data_dum[d].values
                dummy_str = self._data_dum[d].columns.tolist()
                if self._len_num > 0:
                    num_str = self._data_num.columns.tolist()
                    cl = [self._data_num.values, dummy_cols]
                    x = np.concatenate(cl, axis=1)
                else:
                    num_str = None
                    x = dummy_cols
            else:
                dummy_str = None
                if self._len_num > 0:
                    num_str = self._data_num.columns.tolist()
                    x = self._data_num.values
                else:
                    raise ValueError("Need at least one predictor column.")
            if self.verbose:
                print(f"Columns used for {i} - {c}:")
                print(f"Numeric: {num_str}")
                print(f"Categorical: {dummy_str}")

        # return all predictors and target for predictor
        y = self.data_mi[c].values
        return x, y

    def _prep_predictor(self, X, new_data):
        """Make necessary checks and adjustments before prediction"""
        # initial checks before transformation
        check_is_fitted(self, 'statistics_')

        # remove columns in transform if they were removed in fit
        if self._nc:
            wrn = f"{self._nc} dropped in transform since they were not fit."
            warnings.warn(wrn)
            X.drop(self._nc, axis=1, inplace=True)

        # check dataset features are the same for both fit and transform
        X_cols = X.columns.tolist()
        mi_cols = self.data_mi.columns.tolist()
        diff_X = set(X_cols).difference(mi_cols)
        diff_mi = set(mi_cols).difference(X_cols)
        if diff_X or diff_mi:
            raise ValueError("Same columns must appear in fit and predict.")

        # if not error, check if new data
        if new_data:
            self._prep_dataframes(X)
        if not self.scaler is None:
            self._scaler_transform()

    @check_missingness
    def fit(self, X, **kwargs):
        """Get everything that the transform step needs to make predictions"""
        self._prep_dataframes(X)
        self.statistics_ = {}
        if not self.scaler is None:
            self._scaler_fit()
        if self.verbose:
            print("FITTING...")
        # iterate missingness fit using classifier and all remaining columns
        for i, c in enumerate(self.data_mi):
            x, y = self._prep_classifier_cols(X, i, c)
            clf = clone(self.classifier)
            cls_fit = clf.fit(x, y, **kwargs)
            self.statistics_[c] = cls_fit
        return self

    @check_missingness
    def predict(self, X, new_data=True, **kwargs):
        """Make class predictions: 1 for missing 0 for not missing"""
        # predictions for each column using respective fit classifier
        self._prep_predictor(X, new_data)
        if self.verbose:
            print("PREDICTING CLASS MEMBERSHIP...")
        preds_mat = []
        for i, c in enumerate(self.data_mi):
            x, _ = self._prep_classifier_cols(X, i, c)
            cls_fit = self.statistics_[c]
            y_pred = cls_fit.predict(x, **kwargs)
            preds_mat.append(y_pred)

        # store the predictor matrix class membership as a dataframe
        preds_mat = np.array(preds_mat).T
        pred_cols = [f"{cl}_pred" for cl in X.columns]
        self.data_mi_preds = pd.DataFrame(preds_mat, columns=pred_cols)
        return self.data_mi_preds

    @check_missingness
    def predict_proba(self, X, new_data=True, **kwargs):
        """Determine class prediction probabilities for missingness"""
        self._prep_predictor(X, new_data)
        if self.verbose:
            print("PREDICTING CLASS PROBABILITY...")
        preds_mat = []
        for i, c in enumerate(self.data_mi):
            x, _ = self._prep_classifier_cols(X, i, c)
            cls_fit = self.statistics_[c]
            y_pred = cls_fit.predict_proba(x, **kwargs)[:, 1]
            preds_mat.append(y_pred)

        # store the predictor matrix probabilities as a dataframe
        preds_mat = np.array(preds_mat).T
        pred_cols = [f"{cl}_pred" for cl in X.columns]
        self.data_mi_proba = pd.DataFrame(preds_mat, columns=pred_cols)
        return self.data_mi_proba

    def fit_predict(self, X, new_data=False):
        """Convenience method for fit and class prediction"""
        return self.fit(X).predict(X, new_data)

    def fit_predict_proba(self, X, new_data=False):
        """Convenience method for fit and class probability prediction"""
        return self.fit(X).predict_proba(X, new_data)

    @check_missingness
    def gen_test_indices(self, X, thresh=0.5, new_data=False, use_exist=False):
        """Method to indices of false positives for each fitted column"""
        # ALWAYS fit_transform with dataset, as test vals can change
        self.test_indices = {}
        if not use_exist:
            self.fit_predict_proba(X, new_data)

        # loop through missing data indicators, eval new set for missing
        for c in self.data_mi:
            mi_c = self.data_mi[c]
            not_mi = mi_c[mi_c == 0].index
            pred_not_mi = self.data_mi_proba.loc[not_mi, f"{c}_pred"]
            pred_wrong = pred_not_mi[pred_not_mi > thresh].index
            self.test_indices[c] = pred_wrong
            if self.verbose:
                print(f"Test indices for {c}:\n{pred_wrong.values.tolist()}")
        return self

    def gen_test_df(self, X, thresh=.5, m=.05, inplace=False,
                    new_data=False, use_exist=False):
        """Convenience method to return test set as actual dataframe"""
        if not inplace:
            X = X.copy()

        self.gen_test_indices(X, thresh, new_data, use_exist)
        min_num = np.floor(m*len(X.index))
        for c in X:
            ix_ = self.test_indices[c]
            if len(ix_) <= min_num:
                w = f"Fewer than {m*100}% set to missing for {c}"
                warnings.warn(w)
            if X[c].dtype == np.number:
                X.loc[ix_, c] = np.nan
            else:
                X.loc[ix_, c] = None
        return X