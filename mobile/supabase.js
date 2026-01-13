import { createClient } from "@supabase/supabase-js";

const SUPABASE_URL = "https://mgrwrthvhjpmbrvmvkeo.supabase.co";
const SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1ncndydGh2aGpwbWJydm12a2VvIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjgwOTcyNzEsImV4cCI6MjA4MzY3MzI3MX0.Zvzgq3zZv00_3flUniLIk2ZLckylO-SphsKFwZbkTPA";

export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

