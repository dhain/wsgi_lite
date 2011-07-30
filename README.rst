==========================================
Creating Simpler Middleware with WSGI Lite
==========================================

Wouldn't it be nice if writing *correct* WSGI middleware was this simple?

::

    from wsgi_lite import lite, lighten
    
    def latinator(app):
        @lite
        def middleware(environ):
            status, headers, body = app(environ)
            for name, value in headers:
                if name.lower() == 'content-type' and value == 'text/plain':
                    break
            else:
                # Not text/plain, pass the request through unchanged 
                return status, headers, body
                    
            # Strip content-length if present, else it'll be wrong
            headers = [
                (name, value) for name, value in headers
                    if name.lower() != 'content-length'
            ]
            return status, headers, (piglatin(data) for data in body)
    
        # Make sure that `app` can be invoked via the Lite protocol, even
        # if it's a standard WSGI 1 app:
        app = lighten(app)  
        return middleware

If you've seen the ``Latinator`` example from the WSGI PEP, you may recall that
it's about three times this much code and needs two classes, just to do the job
right.  And, if you've ever tried to code a piece of middleware like this,
you'll know just how hard it is to do it correctly.

In fact, as the author of the WSGI PEPs, I have almost never seen a single
piece of WSGI middleware that doesn't break the WSGI protocol in some way that
I couldn't find with a minute or two of code inspection.

But the above ``latinator`` middleware is actually a valid piece of WSGI 1.0
middleware, that can *also* be called with a simpler, Rack-like protocol.  And
all of the hard parts are abstracted away into two decorators: ``@lite``
and ``lighten()``.

The ``@lite`` decorator says, "this function is a WSGI application, but it
expects to be called with an `environ` dictionary, and return a (`status`,
`headers`, `body`) triplet.  And it doesn't use ``start_response()``,
``write()``, or expect to have a ``close()`` method called."

The ``@lite`` decorator then wraps the function in such a way that if it's
called by a WSGI 1 server or middleware, it will act like a WSGI 1 application.
But if it's called with just an `environ` (i.e., without a ``start_response``),
it'll be just like you called the decorated function directly: that is,
you'll get back a (`status`, `headers`, `body`) triplet.

Pretty neat, eh?  But the real magic comes in with the second decorator,
``lighten()``.  ``lighten()`` accepts either a ``@lite`` application or a
WSGI 1 application, and returns a similarly flexible application object.  Just
like the output of the ``@lite`` decorator, the resulting app object can be
called with or without a ``start_response``, and the return protocol it follows
will vary accordingly.

This means that you can either pass a ``@lite`` app or a standard WSGI app
to our ``latinator()`` middleware, and it'll work either way.  And, you can
supply a ``@lite`` or ``lighten()``-ed app to any standard WSGI server or
middleware, and it'll Just Work.

For efficiency, both ``@lite`` and ``lighten()`` are designed to be idempotent:
calling them on already-converted applications returns the app you passed in,
with no extra wrapping.  And, if you call a wrapped application via its native
protocol, no protocol conversion takes place - the original app just gets
called without any conversion overhead.  So, feel free to use both decorators
early and often!


WSGI Extensions and Environment Keys
------------------------------------

One of the subtler edge cases that can arise in writing correct middleware is
that when you call another WSGI app, it's allowed to change the `environ` you
pass in.

And what most people don't realize, is that this means it's *not safe* to pull
things out of the environment *after* you call another WSGI app!

For example, take a look at this middleware example::

    def middleware(environ, start_response):
        response = some_app(environ, start_response)
        if environ.get('PATH_INFO','').endswith('foo'):
            # ...  etc.

Think it'll work correctly?  Think again.  If ``some_app`` is a piece of
routing middleware, it could already have changed ``PATH_INFO``, or any other
environment key.  Likewise, if this middleware looks for server extensions
like ``wsgi.file_wrapper`` or ``wsgiorg.routing_args``, it might end up
reading the child application's extensions, rather than those intended for the
middleware itself.

To help handle these cases, WSGI Lite includes a ``@bind`` decorator that makes
it *much* easier to do things the right way::

    >>> from wsgi_lite import lite, bind
    
    @lite
    @bind(path='PATH_INFO', routing='wsgiorg.routing_args')
    def middleware(environ, path='', routing=((),{})):
        response = some_app(environ, start_response)
        if path.endswith('foo'):
            # ...  etc.

The ``@bind`` decorator takes keyword arguments whose argument names match
argument names on the decorated function, and automatically extracts the
matching keys from the `environ`, passing them on as keyword arguments to the
decorated function.  This automatically ensures that you aren't using
possibly-corrupted keys from your child app(s), *and* lets you specify default
values (via your function's defaults).

Note that ``@bind`` must always come **after** the ``@lite`` decorator, because
the function returned by ``@lite`` doesn't accept any keyword arguments. (Also,
``@bind`` checks your function's signature to make sure it has arguments with
names matching the ones you gave to ``@bind``!)

As a convenience for frequently used extensions or keys, you can save ``bind``
calls and give them names, for example::

    >>> with_routing = bind(routing='wsgiorg.routing_args')

    >>> @lite
    ... @with_routing
    ... def middleware(envrion, routing=((),{})):
    ...     """Some sort of middleware"""

And you can even stack them, or give them names, docstrings, and specify what
module you defined them in::

    >>> with_path = bind(
    ...     'with_path', "Add a `path` arg for ``PATH_INFO``", "__main__",
    ...     path='PATH_INFO'
    ... )

    >>> help(with_path)
    Help on function with_path in module __main__:
    with_path(func)
        Add a `path` arg for ``PATH_INFO``

    >>> @lite
    ... @with_routing
    ... @with_path
    ... def middleware(environ, path='', routing=((),{})):
    ...     """Some combined middleware"""

The underlying ``@bind`` decorator is smart enough to tell when it's being
stacked, and combines decorators so there's only one used, no matter how many
of them you stack.  (As long as they're not intermingled with other decorators,
of course.)

Sometimes, an extension may be known under more than one name - for example,
an ``x-wsgiorg.`` extension vs. a ``wsgiorg.`` one, or a similar extension
provided by different servers.  You could of course bind them to different
arguments, but it's generally simpler to just bind to a tuple::

    >>> @bind(routing=('wsgiorg.routing_args', 'x-wsgiorg.routing_args'))
    ... def middleware(envrion, routing=((),{})):
    ...     """Some sort of middleware"""

This will check the environment for the named extensions in the order listed,
and replace `routing` with the first one matched.

For more elaborate use cases, you can also pass callables to ``bind``.  They'll
be called with the environ, and must return an iterable with zero or more
items.  Zero items means the lookup failed, and the default should be used.
Otherwise, the first item is used as the keyword argument.  Example::

    >>> class MyRequest(object):
    ...     def __init__(self, environ):
    ...         self.environ = environ
    ...
    ...     @classmethod
    ...     def bind(cls, environ):
    ...         yield cls(environ)

    >>> with_request = bind(request=MyRequest.bind)

Now, ``@with_request`` will create a ``MyRequest`` instance wrapping the
`environ` of the decorated function, and provide it via the ``request`` keyword
argument.

This can also be used to do things like accessing environment-cached objects,
such as sessions::

    >>> class MySession(object):
    ...     def __init__(self, environ):
    ...         self.environ = environ
    ...
    ...     @classmethod
    ...     def bind(cls, environ):
    ...         session = environ.get('myframework.MySession')
    ...         if session is None:
    ...             session = environ['myframework.MySession'] = cls(environ)
    ...         yield session

    >>> with_session = bind(session=MySession.bind)

The possibilities are pretty much endless -- and much more in keeping with my
original vision for how WSGI was supposed to help dissolve web frameworks into
*web libraries*.  (That is, things you can easily mix and match without 
every piece of code you use having to come from the same place.)


``close()`` and Resource Cleanups
---------------------------------

So, there's some good news and some bad news about ``close()`` and resource
cleanups in WSGI Lite.

The *good* news is, ``@lite`` middleware is **not** required to call a body
iterator's ``close()`` method.  And if your app or middleware doesn't need to
do any post-request resource cleanup, or if it just returns a body sequence
instead of an iterator or generator, then you don't need to worry about
resource cleanup at all.  Just write the app or middleware and get on with your
life.  ;-)

Now, if you *are* yielding body chunks from your WSGI apps, you might
want to consider *just not doing that*.

That's because, if you don't yield chunks, you can write normal, synchronous
code that won't have any of the problems I'm about to introduce you to...
problems that your *existing WSGI apps already have*, but you probably don't
know about yet!

(People often object when I say that typical application code should **never**
produce its output incrementally...  but the hard problem of proper resource
cleanup when doing so, is one of the reasons I'm always saying it.)

Anyway, if you *must* produce your response in chunks, *and* you need to
release some resources as soon as the response is finished,  you need to use
the ``@wsgi_lite.with_closing`` decorator, e.g::

    from wsgi_lite import lite, with_closing

    @lite
    @with_closing
    def my_app(environ, closing):

        def my_body():
            try:
                # allocate some resources
                ...
                yield chunk
                ...
            finally:
                # release the resources

        return status, headers, closing(my_body())

Under the hood, the ``@with_closing`` decorator is actually an abbreviation for
``@bind(closing='wsgi_lite.register_close')``.  That is, it helps you use WSGI
Lite's resource cleanup extension to the WSGI protocol.

The protocol extension (accessed as ``closing()`` in the function body above)
is used to register an iterator (or other resource) so that its ``close()``
method will be called at the end of the request, even if the browser
disconnects or a piece of middleware throws away your iterator to use its own
instead.

Do note that the *order* in which you make ``closing()`` calls is important,
if you call it more than once.  Items are closed in the order they are
registered, so if you register a resource before calling another app, then that
resource might be closed before the app's cleanup is run...  and that could be
a bad thing if the app got access to the resource somehow.  So, it's best if
you do all your ``closing()`` calls *after* any child apps have had a chance
to do theirs.  (Really, the simplest thing is probably going to be to just
doing all your cleanup in a body iterator's ``try/finally``, anyway.)

Okay, so *that* was the bad news.  Not that bad, though, is it?  You need
another decorator, and you need to pay attention to the order of resource
closing.  That's it!

Really, the rest of this section is all about what will happen if you *don't*
use the decorator, or if you try to do resource cleanup in a standard WSGI app
without the benefit of WSGI Lite.

As long as you use the decorator, your app's resource cleanup will work *at
least* as well as -- and probably much better than! -- it would work under
plain WSGI.  (And you can make it work even better still if you wrap your
entire WSGI stack with a ``lighten()`` call...  but more on that will have to
wait until the end of this section.)

So, just to be clear, the rest of this section is about flaws and weaknesses
that exist in *standard* WSGI's resource management protocol, and what WSGI
Lite is doing to work around them.

What flaws and weaknesses?  Well, consider the example above.  Why does it
*need* the ``@with_closing`` decorator?  After all, doesn't Python guarantee
that the ``finally`` block will be executed anyway?

Well, yes and no.  First off, if the generator is called but never iterated
over, the ``try`` block won't execute, and so neither will the ``finally``.
So, it depends on what the caller does with the generator.  For example, if
the browser disconnects before the body is fully generated, the server might
*just stop iterating* over it.

Okay, but won't garbage collection take care of it, then?

Well, yes and no.  *Eventually*, it'll be garbage collected, but in the
meantime, your app has a resource leak that might be exploitable to deny
service to the app: just start up a resource-using request, then drop the
connection over and over until the server runs out of memory or file handles
or database cursors or whatever.

Now, under the WSGI standard, middleware and servers are *supposed* to call
``close()`` on a response iterator (if it has one), whenever they stop
iterating -- regardless of whether the iteration finished normally, with an
error, or due to a browser disconnect.

In practice, however, **most** WSGI middleware is broken and doesn't call
``close()``, because 1) doing so usually makes your middleware code really
*really* complicated, and 2) nobody understands why they *need* to call
``close()``, because everything *appears* to work fine without it.  (At least,
until some black-hat finds your latent denial-of-service bug, anyway.)

So, WSGI Lite works around this by giving you a way to be *sure* that
``close()`` will be called, using a tiny extension of the WSGI protocol that
I'll explain in the next section...  but only if you care about the details.

Otherwise, just use ``@with_closing`` if you need resource cleanup in your
body iterator, and be happy that you don't need to know anything more.  ;-)

Well, actually, you do need to know ONE more thing...  If your outermost
``@lite`` application is wrapped by any off-the-shelf WSGI middleware, you
probably want to wrap the outermost piece of middleware with a ``lighten()``
call.  This will let WSGI Lite make sure that *your* ``close()`` methods get
called, even if the middleware that wraps you is broken.

(Technically speaking, of course, there's no way to be *sure* you're not being
wrapped by middleware, so it's not really a cure-all unless your WSGI server
natively supports the extension described in the next section.  Hopefully,
though, we'll put the extension into a PEP soon and all the popular servers
will provide it in a reasonable time period.)


The ``wsgi_lite.register_close`` Extension
------------------------------------------

WSGI Lite uses a WSGI server extension called ``wsgi_lite.register_close``,
that lives in the application's `environ` variable.  The ``@lite`` and
``lighten()`` decorators automatically add this extension to the environment,
if they're called from a WSGI 1 server or middleware, and the key doesn't
already exist.  (This is why you don't need a default value for the ``closing``
argument when using ``@with_closing``, by the way: the key will always be
available to a ``@lite`` app or middleware component, or any sub-app or
sub-middleware that inherits the same environment.)

The value for this key is a callback function that takes one argument: an
object whose ``close()`` method is to be called at the end of the request.
For convenience, the passed-in object is returned back to the caller, so you
can use it in a way that's reminiscent of ``with closing(file('foo')) as f:``.

Anyway, the idea here is that a server (or middleware component) accepts these
registrations, and then closes all the resources (or generators) when the
request is finished.

Objects are closed in the order in which they're registered, so that inner
apps' resources are released prior to middleware resources being released.
(In other words, if an app is using a resource that it received from middleware
via its `environ`, that resource will still be usable during the app's
``close()`` processing or ``finally`` blocks.)

Objects registered with this extension **must** have ``close()`` methods, and
the methods **must** be idempotent: that is, it must be safe to call them
more than once.  (That is, calling ``close()`` a second time **must not**
raise an error.)

Currently, the handling of errors raised by ``close()`` methods is undefined,
in that WSGI Lite doesn't yet handle them.  ;-)  (When I have some idea of how
best to handle this, I'll update this bit of the spec.)

I would like to encourage WSGI server developers to support this extension if
they can.  While WSGI Lite implements it via middleware (in both the ``@lite``
and ``lighten()`` decorators), it's best if the WSGI origin server does it,
in order to bypass any broken middleware in between the server and the app.
(And, if a ``@lite`` or ``lighten()`` app is invoked from a server or
middleware that already implements this extension, it'll make use of the
provided implementation, instead of adding its own.)

Now, if for some reason you want to use this extension directly in your code
without using ``@with_closing``, *please* remember the following two caveats:

* The WSGI spec allows called applications to modify the `environ`.  This
  means that you **must** retrieve the extension *before* you pass the
  `environ` to another app.  (That's why we have ``@bind``, remember?)

* Since you don't usually have the object with the ``close()`` method ready
  until near the end of request processing, *and* because the resources might
  be used by any apps you call, you **should** wait until after the child
  request has had a chance to register its resources, before you register
  yours.

These two requirements are in fundamental conflict: you must *retrieve* the
extension as early as possible, but *use* it as late as possible.  So, if
you're not using ``@with_closing``, be sure to do something like this instead::

    def an_app(environ, start_response):
        closing = environ['wsgi_lite.register_close']
        ...
        return closing(someiter)

Got it?  Good.


Other Protocol Details
----------------------

Technically, WSGI Lite is a protocol as well as an implementation.  And there's
still one more thing to cover (besides the Rack-style calling convention and
``register_close`` extension) that distinguishes it from standard WSGI.  

Applications supporting the "lite" invocation protocol (i.e. being called
without a ``start_response`` and returning a status/header/body triplet), are
identified by a ``__wsgi_lite__`` attribute with a ``True`` value.  (``@lite``
and ``lighten()`` add this for you automatically.)

Any app *without* the attribute, however, is assumed to be a standard WSGI 1
application, and thus in need of being ``lighten()``-ed before it can be
called via the WSGI Lite protocol.

(If you want to check for this attribute, or add it to an object that natively
supports WSGI Lite, you can use the ``wsgi_lite.is_lite()`` and
``wsgi_lite.mark_lite()`` APIs, respectively.  But even if you want to, you
probably don't  *need* to, because if you call ``@lite`` or ``lighten()`` on
an object that's already "lite", it's returned unchanged.  So it's easier to
just always call the appropriate decorator, rather than trying to figure out
*whether* to call it.  Idempotence == **good**!)  

Anyway, the rest of the protocol is defined simply as a stripped down WSGI,
minus ``start_response()``, ``write()``, and ``close()``, but with the addition
of the ``wsgi_lite.register_close`` key.  That's pretty much it.


Limitations
-----------

You knew there had to be a catch, right?

Well, in this case, there are two.

First, if you ``lighten()`` a standard WSGI app that uses ``write()`` calls
instead of using a response iterator, you **must** have the ``greenlet``
library installed, or you'll get an error when ``write()`` is called.

Why?  Well, it's complicated.  But the chances are pretty good that you don't
have any code that uses ``write()``, and if you do, well, ``greenlet`` works on
lots of platforms and Python versions.

And second, speaking of Python versions, if you're using a version less than
2.5, you need to have ``DecoratorTools`` installed as well.  Python 2.4 doesn't
have ``functools`` in the standard library.)

Second, no, third...  wait, I'll come in again.

*Chief* amongst the limitations of WSGI Lite is that it cannot work around
broken WSGI 1 middleware that lives *above* your application in the call stack!

So, until standard WSGI servers support the ``wsgi_lite.register_close``
extension, you can (and should) work around this by wrapping your outermost
middleware with a ``lighten()`` call.

Last, but not least, the ``lighten()`` wrapper doesn't support broken WSGI
apps that call ``write()`` from inside their returned iterators.  While many
servers allow it, the WSGI specification forbids it, and to support it in
WSGI Lite would force *all* wrapped WSGI 1 apps to pay in the form of
unnecessary greenlet context switches, even if they never used ``write()`` at
all.

Since the current "word on the street" says that very few WSGI apps use
``write()`` at all, I figure it's okay to blow up on the even smaller number
that are also spec violators, rather than burden *all* apps with extra overhead
just to support the ill-behaved ones.


Current Status
--------------

The code in this repository is experi-mental, and possibly very-mental or
just plain detri-mental.  It is not seriously tested or battle-hardened as yet:
there are just some very basic acceptance tests and validation, enough to show
a few basics working.  (See the "To-Test" list in ``tests.txt`` for what major
tests are still needed.)

So, I've really just thrown this out there for people to see and play with
early.  Stuff may change, break, or this could all have been a really stupid
idea that doesn't actually work.  Don't throw this into production or even
serious development just yet: it might *look* like it works, but you'd be wiser
to wait until there's something more like full test coverage.  But if you're
just experimenting with it to see how it works or whether you like it, go for
it!  (And if you have any feedback, I'd love to hear from you...  preferably
via the Web-SIG mailing list.)

Oh, and last, but not least...  this package is under the Apache license, since
that's what the PSF uses for software contributed to Python, and I hope to see
this protocol in a PEP and perhaps the stdlib in the future.  (Assuming we
don't find some sort of glaring hole in the protocol or concept, of course.)

