import Onboarding from "./components/Onboarding";

function App() {
  return <Onboarding onComplete={(data) => console.log("done!", data)} />;
}

export default App;