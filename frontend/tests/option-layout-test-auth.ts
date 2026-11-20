// Resolved only by the guarded serve-only test Vite config.
const session = () => fetch(`${import.meta.env.VITE_API_BASE_URL}/__test_session?role=${
  localStorage.getItem("layout-browser-role") === "STUDENT" ? "STUDENT" : "ADMIN"
}`).then((response) => {
  if (!response.ok) throw new Error("Local layout test session unavailable");
  return response.json();
});
export const isNeonAuthConfigured = true;
export const getNeonAuthToken = async () => (await session()).token;
export const getCurrentAuthUser = async () => (await session()).user;
export const signOutNeonAuth = async () => {};
const unsupported = async () => { throw new Error("Use the isolated browser test identity"); };
export const signInWithEmail = unsupported;
export const signUpWithEmail = unsupported;
export const signInWithGoogle = unsupported;
export const sendEmailVerificationCode = unsupported;
export const verifyEmailCode = unsupported;
export const requestPasswordCode = unsupported;
export const resetPasswordWithCode = unsupported;
