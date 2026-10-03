export function hasAuthenticatedSession(status, user) {
  return status === "connected" || Boolean(user);
}

export function getSessionRefreshStartStatus(status, user) {
  return hasAuthenticatedSession(status, user) ? status : "connecting";
}

export function getSessionRefreshErrorState({ errorMessage, previousTokenInfo, previousUser }) {
  if (previousUser) {
    return {
      error: errorMessage,
      status: "connected",
      tokenInfo: previousTokenInfo || null,
      user: previousUser,
    };
  }
  return {
    error: errorMessage,
    status: "error",
    tokenInfo: null,
    user: null,
  };
}
