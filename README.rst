==========================================
Creating Simpler Middleware with WSGI Lite
==========================================

Wouldn't it be nice if writing *correct* WSGI middleware was this simple?

    >>> from wsgi_lite import lite, lighten
    
    >>> def latinator(app):
    ...     @lite
    ...     def middleware(environ):
    ...         status, headers, body = app(environ)
    ...         for name, value in headers:
    ...             if name.lower() == 'content-type' and value == 'text/plain':
    ...                 break
    ...         else:
    ...             # Not text/plain, pass the request through unchanged 
    ...             return status, headers, body
    ...                 
    ...         # Strip content-length if present, else it'll be wrong
    ...         headers = [
    ...             (name, value) for name, value in headers
    ...                 if name.lower() != 'content-length'
    ...         ]
    ...         return status, headers, (piglatin(data) for data in body)
    ... 
    ...     # Make sure that `app` can be invoked via the Lite protocol, even
    ...     # if it's a standard WSGI 1 app:
    ...     app = lighten(app)  
    ...     return middleware

If you've seen the ``Latinator`` example from the WSGI PEP, you may recall that
it's about three times this much code and needs two classes, just to do the job
right.  And, if you've ever tried to code a piece of middleware like this,
you'll know just how hard it is to do it correctly.

In fact, as the author of the WSGI PEPs, I have almost never seen a single
piece of WSGI middleware that doesn't break the WSGI protocol in some way that
I couldn't find with a minute or two of code inspection.

But the above piece of middleware is actually a valid piece of WSGI 1.0
middleware, that can *also* be called with a simpler, Rack-like protocol.  And
all of the hard parts are abstracted away into two decorators: ``@lite``
and ``lighten()``.

The ``@lite`` decorator says, "this function is a WSGI application, but it
expects to be called with an `environ` dictionary, and return a (`status`,
`headers`, `body`) triplet.  And it doesn't use ``start_response()``,
``write()``, or expect to have a ``close()`` method called.

The ``@lite`` decorator then wraps the function in such a way that if it's
called by a WSGI 1 server or middleware, it will act like a WSGI 1 application.
But if it's called with just an `environ` (i.e., without a ``start_response``),
it'll be just like you called the decorated function directly: that is,
you'll get back a (`status`, `headers`, `body`) triplet.

Pretty neat, eh?  But the real magic comes in with the second decorator,
``lighten()``.  ``lighten()`` accepts either a ``@lite`` application or a
WSGI 1 application, and returns a similary flexible application object.  Just
like the output of the ``@lite`` decorator, the resulting app object can be
called with or without a ``start_response``, and the protocol it follows will
vary accordingly.

This means that you can either pass a ``@lite`` app or a standard WSGI app
to our ``latinator()`` middleware, and it'll work either way.  And, for
efficiency, both ``@lite``and ``lighten()`` are designed to be idempotent:
calling them on already-converted apps has no effect, and if you call a
wrapped application via its native protocol, no protocol conversion takes
place.


``close()`` and Cleanups
------------------------

In addition to the calling protocol change, WSGI Lite makes one more addition
to the standard WSGI protocol: a ``wsgi_lite.add_cleanup`` key in the `environ`
dictionary.  This entry, if present (and ``@lite`` guarantees it will be),
is a callable taking a callback function to be invoked at the end of the
current request.

This is a middleware-friendly alternative to WSGI's ``close()`` protocol, which
most middleware doesn't implement correctly, anyway!

By adding this environment key, applications that need cleanup to happen can
just register a callback for it, and let the server take care of it.
Intervening middleware can ignore it, or substitute their own ``add_cleanup``
callback if for some reason the middleware needs to manage the wrapped app's
callbacks.

Internally, the ``wsgi_lite`` library both automatically registers any WSGI 1
``close()`` methods as cleanup callbacks, *and* exports a ``close()`` method
to fire off those callbacks when the enclosing WSGI 1 server calls it.  In
this way, middleware need never worry about these WSGI implementation details.


The Protocol
------------

Technically, WSGI Lite is a protocol as well as an implementation.
Applications supporting the "lite" invocation protocol are marked by a
``__wsgi_lite__`` attribute with a ``True`` value.  Any other app is assumed
to be a standard WSGI 1 application, and thus in need of ``lighten()`` before
it can be called via the WSGI Lite protocol.

The rest of the protocol is defined simply as a stripped down WSGI, minus
``start_response()``, ``write()``, and ``close()``, but with the addition of
the ``wsgi_lite.add_cleanup`` key.


Limitations
-----------

You knew there had to be a catch, right?

Well, here's the catch: if you wrap a WSGI 1 app that uses ``write()`` calls
instead of using a response iterator, you **must** have the ``greenlet``
library installed, or you'll get an error when ``write()`` is called.

Why?  Well, it's complicated.  But the chances are pretty good that you don't
have any code that uses ``write()``, and if you do, well, ``greenlet`` works on
lots of platforms and Python versions.

Oh, and speaking of Python versions, if you're using a version less than 2.5,
you need to have ``DecoratorTools`` installed as well.  Python 2.4 doesn't have
``functools`` in the standard library.


Current Status
--------------

The code in this repository is experimental, and possibly mental.  It is not
tested in any serious way as yet, or even a non-serious way.  I've thrown this
out there for people to see and play with early.  Stuff may change, break,
or this could all have been a really stupid idea that doesn't actually work.
You have been warned.

(Oh, and it's under an ASF license, since that's what the PSF uses for
contributions... i.e., I anticipate this potentially becoming PEPpable and
stdlib-able in the future, if we don't find some sort of glaring hole in it.)

