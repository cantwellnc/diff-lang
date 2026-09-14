toy experiment doing "program differencing". 

goal: tell when 2 programs are different, and provides a notion of "distance" between them. 

loops etc. are not supported so this is decidable. programs get translated to z3 formulas are classified in the following ways: 
- they agree everywhere, i.e. are proved by z3 to be the same (extensionally).
- they agree nowhere => solver produces counterexample 
- they agree conditionally => there exist inputs I where the fns agree, so you can add additional constraints of the form `... /\ inputs \in I` to the program formulae to make them equal. The #
  of additional conditions needed is a proxy for "distance" between the programs

