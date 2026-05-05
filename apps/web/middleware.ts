export { auth as middleware } from "@/auth";

export const config = {
  // Apply auth middleware to all /chat routes
  matcher: ["/chat/:path*"],
};
