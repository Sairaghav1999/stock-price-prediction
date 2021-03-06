import matplotlib.pyplot as plt
import numpy as np
import os
import pickle
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import cross_validate, GridSearchCV, learning_curve, TimeSeriesSplit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVR
from sklearn.tree import DecisionTreeRegressor
from setuplogger import logger


class BuildModels(object):
	def __init__(self):
		"""
		Constructor for the class.
		"""
		self.built_models_dict = {}
		self.model_scores_dict = {}
		self.saved_models_dir = "saved_models"
		self.models_dict = {
			"Decision Tree Regressor": DecisionTreeRegressor(),
			"Linear Regression": LinearRegression(),
			"Random Forest Regressor": RandomForestRegressor(),
			"SVR": SVR()
		}
		self.parameters_dict = {
			"Decision Tree Regressor": {"max_depth": [200]},
			"Linear Regression": {"n_jobs": [None, -1]},
			"Random Forest Regressor": {"max_depth": [200], "n_estimators": [100]},
			"SVR": {"kernel": ["rbf", "linear"], "degree": [3], "gamma": ["scale"]}
		}
		self.saved_models_path = "{}/{}".format(os.getcwd(), self.saved_models_dir)
		self.learning_curve_dir_path = "{}/learning_curve_plots".format(os.getcwd())
		os.mkdir(self.saved_models_path) if not os.path.exists(self.saved_models_path) else None
		os.mkdir(self.learning_curve_dir_path) if not os.path.exists(self.learning_curve_dir_path) else None

	def build_model(self, model_name, preprocessed_data_dict, force_build):
	
		logger.info("----------------Building model using {}----------------".format(model_name))
		model_dict = {}
		model_scores_dict = {}
		curr_dir = os.getcwd()
		for ticker_symbol, preprocessed_data in preprocessed_data_dict.items():
			[X, X_forecast, y] = preprocessed_data
			tscv = TimeSeriesSplit(n_splits=5)
			ticker_symbol = ticker_symbol.replace("/", "_")
			if force_build or not os.path.exists(
					"{}/{}_{}_model.pickle".format(self.saved_models_path, model_name,	ticker_symbol)):
				# X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)
				# Create a cv iterator for splitting train and test data using TimeSeriesSplit
				# Optimize the hyperparameters based on the cross validation scores
				optimized_model = self.optimize_hyperparameters(model_name, tscv)
				model = make_pipeline(StandardScaler(), optimized_model)
				X_train, X_test, y_train, y_test = self.get_train_and_test_data(X, y, tscv)
				model.fit(X_train, y_train)
				self.save_to_pickle_file(model_name, ticker_symbol, model, "model")
			else:
				model = self.load_from_pickle_file(model_name, ticker_symbol, "model")
				X_train, X_test, y_train, y_test = self.get_train_and_test_data(X, y, tscv)
			# Training score
			confidence_score = model.score(X_test, y_test)
			# Plot learning curves
			title = "{}_{}_Learning Curves".format(model_name, ticker_symbol)
			save_file_path = "{}/learning_curve_plots/{}_{}.png".format(curr_dir, model_name, ticker_symbol)
			# Create the CV iterator
			self.plot_learning_curve(model, title, X, y, save_file_path, cv=tscv)
			# Cross validation
			cv_scores = cross_validate(model, X=X, y=y, cv=tscv)
			logger.info("Training score for {} = {}".format(ticker_symbol, confidence_score))
			logger.debug("Cross validation scores for {} = {}".format(ticker_symbol, cv_scores["test_score"]))
			logger.info("Cross validation score for {} = {} +/- {}".format(
				ticker_symbol, cv_scores["test_score"].mean(), cv_scores["test_score"].std() * 2))
			logger.debug("Cross validation scoring time = {}s".format(cv_scores["score_time"].sum()))
			model_dict[ticker_symbol] = model
			model_scores_dict[ticker_symbol] = confidence_score
		return model_dict, model_scores_dict

	def build_models(self, model_names, preprocessed_data_dict, force_build=False):
	
		for model_name in model_names:
			model_dict, model_scores_dict = self.build_model(model_name, preprocessed_data_dict, force_build)
			self.built_models_dict[model_name] = model_dict
			self.model_scores_dict[model_name] = model_scores_dict
		return self.built_models_dict, self.model_scores_dict

	def get_built_models(self):

		if self.built_models_dict:
			return self.built_models_dict
		else:
			logger.info("No models found. Run build_models first and then call this method.")
			exit(1)

	def get_train_and_test_data(self, X, y, tscv):
		split_data = []
		for train_indices, test_indices in tscv.split(X):
			X_train, X_test = X[train_indices], X[test_indices]
			y_train, y_test = y[train_indices], y[test_indices]
			split_data.append((X_train, X_test, y_train, y_test))
		# Get cross validation score for the last index as it will have the most training data which is good for time
		# series data
		best_split_index = -1
		X_train, X_test, y_train, y_test = split_data[best_split_index]
		logger.debug("Last train_data size = {}".format(len(X_train) * 100 / len(X)))
		return X_train, X_test, y_train, y_test

	def load_from_pickle_file(self, model_name, ticker_symbol, obj_name):
		logger.info("Loading {} model for {} from pickle file".format(model_name, ticker_symbol))
		pickle_in = open("{}/{}_{}_{}.pickle".format(
			self.saved_models_dir, model_name, ticker_symbol, obj_name), "rb")
		loaded_obj = pickle.load(pickle_in)
		return loaded_obj

	def optimize_hyperparameters(self, model_name, cv_iterator):
		logger.debug("Optimizing hyper-parameters")
		parameters_dict = self.parameters_dict[model_name]
		model = self.models_dict[model_name]
		# Hyperparameter optimization
		optimized_model = GridSearchCV(estimator=model, param_grid=parameters_dict, cv=cv_iterator)
		return optimized_model

	def plot_learning_curve(self, estimator, title, X, y, save_file_path, ylim=None, cv=None,
													train_sizes=np.linspace(.1, 1.0, 5)):
		logger.info("Plotting {}".format(title))
		plt.figure()
		plt.title(title)
		if ylim is not None:
			plt.ylim(*ylim)
		plt.xlabel("Training examples")
		plt.ylabel("Score")
		train_sizes, train_scores, test_scores = learning_curve(
			estimator, X, y, cv=cv, train_sizes=train_sizes)
		train_scores_mean = np.mean(train_scores, axis=1)
		train_scores_std = np.std(train_scores, axis=1)
		test_scores_mean = np.mean(test_scores, axis=1)
		test_scores_std = np.std(test_scores, axis=1)
		plt.grid()

		plt.fill_between(train_sizes, train_scores_mean - train_scores_std, train_scores_mean + train_scores_std, alpha=0.1,
										 color="r")
		plt.fill_between(train_sizes, test_scores_mean - test_scores_std, test_scores_mean + test_scores_std, alpha=0.1,
										 color="g")
		plt.plot(train_sizes, train_scores_mean, 'o-', color="r", label="Training score")
		plt.plot(train_sizes, test_scores_mean, 'o-', color="g", label="Cross-validation score")

		plt.legend(loc="best")
		plt.savefig("{}".format(save_file_path))
		plt.close()

	def save_to_pickle_file(self, model_name, ticker_symbol, obj_to_be_saved, obj_name):
		logger.info("Saving {} model for {} to pickle file".format(model_name, ticker_symbol))
		pickle_out = open("{}/{}_{}_{}.pickle".format(
			self.saved_models_dir, model_name, ticker_symbol, obj_name), "wb")
		pickle.dump(obj_to_be_saved, pickle_out)
		pickle_out.close()
