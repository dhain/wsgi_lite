def test(app, environ={}, form={}, **kw):
    """Print the output of a WSGI app

    Runs `app` as a WSGI application and prints its output.  If an untrapped
    error occurs in `app`, it drops into the ``pdb`` debugger's post-mortem
    debug shell (using ``sys.__stdout__`` if ``sys.stdout`` has been replaced).

    Any keyword arguments are added to the environment used to run `app`.  If
    a keyword argument begins with ``wsgi_``, the ``_`` is replaced with a
    ``.``, so that you can set e.g. ``wsgi.multithread`` using a
    ``wsgi_multithread`` keyword argument.

    If a non-empty `form` dictionary is provided, it is treated as a collection
    of fields for a form ``POST``. The ``REQUEST_METHOD`` will default to
    ``POST``, and the default ``CONTENT_LENGTH``, ``CONTENT_TYPE``, and
    ``wsgi.input`` values will be appropriately set (but can still be
    overridden by explicit keyword arguments or the `environ` argument).

    Any `form` values that are not instances of ``basestring`` are assumed to
    be *sequences* of values, and will result in multiple name/value pairs
    being added to the encoded data sent to the application.

    Any WSGI-required variables that are not specified by `environ`, `form`, or
    keyword arguments, are initialized to default values using the
    ``wsgiref.util.setup_testing_defaults()`` function.
    """

    from wsgiref.util import setup_testing_defaults
    from wsgiref.handlers import BaseCGIHandler
    from StringIO import StringIO
    from urllib import quote_plus

    environ = environ.copy()
    for k, v in kw.items():
        if k.startswith('wsgi_'):
            environ[k.replace('_','.',1)] = v
        else:
            environ[k] = v



    if form:
        encoded = []
        for k, v in form.items():
            if isinstance(v,basestring):
                v = [v]
            for v in v:
                encoded.append('%s=%s' % (quote_plus(k), quote_plus(v)))
        encoded = '&'.join(encoded)
        environ.setdefault('wsgi.input', StringIO(encoded))
        environ.setdefault('CONTENT_LENGTH', str(len(encoded)))
        environ.setdefault('CONTENT_TYPE', 'application/x-www-form-urlencoded')
        environ.setdefault('REQUEST_METHOD', 'POST')

    setup_testing_defaults(environ)
    stdout = StringIO()
    stderr = environ['wsgi.errors']

    def wrapper(env, start):
        try:
            return app(env, start)
        except:
            stdout = sys.stdout
            try:
                if stdout is not sys.__stdout__:
                    sys.stdout = sys.__stdout__
                import pdb
                pdb.post_mortem(sys.exc_info()[2])
            finally:
                sys.stdout = stdout
            raise

    BaseCGIHandler(
        environ['wsgi.input'], stdout, stderr, environ,
        environ['wsgi.multithread'], environ['wsgi.multiprocess']
    ).run(wrapper)
    print stdout.getvalue().replace('\r\n','\n')
    if stderr.getvalue():
        print "--- Log Output ---"
        print stderr.getvalue().replace('\r\n','\n')


def additional_tests():
    import doctest
    return doctest.DocFileSuite(
        'tests.txt',
        optionflags=doctest.ELLIPSIS|doctest.REPORT_ONLY_FIRST_FAILURE,
    )



































