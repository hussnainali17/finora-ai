// The access token lives ONLY in memory: never localStorage/sessionStorage, so an XSS payload
// cannot read a long-lived credential. The refresh token is an HttpOnly cookie the browser
// manages and JavaScript can never see. A page reload silently re-authenticates via the cookie.
let accessToken: string | null = null;

export const tokenStore = {
  get: (): string | null => accessToken,
  set: (token: string | null): void => {
    accessToken = token;
  },
};
