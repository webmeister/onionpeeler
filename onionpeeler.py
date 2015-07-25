#!/usr/bin/env python
import collections
import flask
import os
import os.path
import pygal
import tempfile
import zipfile

import config
import containers


app = flask.Flask(__name__)
relays = containers.Relays(config.onionoo_mirrors, config.refresh_interval)
operators = containers.Operator('Tor', config.operators)


def render_groups(base, field, path=''):
	chart = pygal.Pie()
	chart.title = '{} Nodes ({})'.format(base.name, field)
	combined = 0

	for group in sorted(base.subgroups.values(), key=lambda x:x.name.lower()):
		value = sum(relay.get(field, 0) for relay in relays.search(group))
		chart.add(group.name, [{
			'value': value,
			'xlink': {
				'href': flask.url_for('organisations', path=path + ('/' if path else '') + group.name, **dict(flask.request.values.lists())),
				'target': '_self',
			},
		}])
		combined += value

	return chart, combined


@app.route('/pie.svg')
def overview():
	field = flask.request.values.get('stats', config.default_field)
	chart, value = render_groups(operators, field)
	chart.add('other', [{
		'value': sum(relay.get(field, 0) for relay in relays.search()) - value,
	}])

	return chart.render_response()


@app.route('/pie/<path:path>.svg')
def organisations(path):
	field = flask.request.values.get('stats', config.default_field)

	try:
		operator = operators.resolve(path.split('/'))
	except KeyError:
		flask.abort(404)

	if operator.subgroups:
		chart, _ = render_groups(operator, field, path=path)
	else:
		chart = pygal.Pie()
		chart.title = operator.name + ' Nodes ({})'.format(field)
		for relay in sorted(relays.search(operator), key=lambda x:x.get('nickname', 'Unnamed').lower()):
			chart.add(relay.get('nickname', 'Unnamed'), [{
				'value': relay.get(field, 0),
				'xlink': {
					'href': 'https://atlas.torproject.org/#details/' + relay['fingerprint'],
					'target': '_top',
				},
			}])

	return chart.render_response()


@app.route('/map.svg', defaults={'path': None})
@app.route('/map/<path:path>.svg')
def map(path):
	operator = operators
	if path:
		try:
			operator = operator.resolve(path.split('/'))
		except KeyError:
			flask.abort(404)

	chart = pygal.Worldmap()
	chart.title = operator.name + ' Nodes'

	if operator.subgroups:
		for group in sorted(operator.subgroups.values(), key=lambda x:x.name):
			chart.add(group.name, collections.Counter(relay.get('country', None) for relay in relays.search(group)))
	else:
		chart.add(operator.name, collections.Counter(relay.get('country', None) for relay in relays.search(operator)))

	return chart.render_response()


@app.route('/source.zip')
def download():
	with tempfile.SpooledTemporaryFile() as f:
		with zipfile.ZipFile(f, 'w') as zf:
			basepath = os.path.dirname(__file__)
			for root, dirs, files in os.walk(basepath):
				for dir in list(dirs):
					if dir.startswith('.') or dir == '__pycache__':
						dirs.remove(dir)
				for file in files:
					target = os.path.join(root, file)
					zf.write(target, os.path.relpath(target, basepath))
		f.seek(0)
		content = f.read()

	return flask.Response(content, headers={'Content-Disposition': 'attachment;filename=source.zip'})


if __name__ == '__main__':
	app.run(threaded=True, debug=True)
