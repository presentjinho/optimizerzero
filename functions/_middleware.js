function unauthorized() {
  return new Response("Authentication required.", {
    status: 401,
    headers: {
      "WWW-Authenticate": 'Basic realm="OptimizerZero private preview"',
      "Cache-Control": "no-store",
    },
  });
}

function decodeBasicAuth(header) {
  if (!header || !header.startsWith("Basic ")) return null;

  try {
    const decoded = atob(header.slice("Basic ".length));
    const separator = decoded.indexOf(":");
    if (separator < 0) return null;
    return {
      user: decoded.slice(0, separator),
      password: decoded.slice(separator + 1),
    };
  } catch {
    return null;
  }
}

export async function onRequest(context) {
  const expectedUser = context.env.OPTIMIZERZERO_USER || "presentjinho";
  const expectedPassword = context.env.OPTIMIZERZERO_PASSWORD;

  if (!expectedPassword) {
    return new Response("Private preview password is not configured.", {
      status: 503,
      headers: { "Cache-Control": "no-store" },
    });
  }

  const credentials = decodeBasicAuth(context.request.headers.get("Authorization"));
  if (!credentials) return unauthorized();

  if (credentials.user !== expectedUser || credentials.password !== expectedPassword) {
    return unauthorized();
  }

  const response = await context.next();
  const guarded = new Response(response.body, response);
  guarded.headers.set("Cache-Control", "no-store");
  guarded.headers.set("Vary", "Authorization");
  return guarded;
}
