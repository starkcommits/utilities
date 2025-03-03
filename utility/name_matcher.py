import re
from difflib import SequenceMatcher
import frappe
from frappe.utils import cint, flt
from frappe import _

# Note: Frappe avoids external dependencies where possible
# This implementation avoids external dependencies like fuzzywuzzy and jellyfish
# But you can install them if needed in your environment

class NameMatcher:
    """
    A class that provides various methods for name matching and scoring.
    """
    
    def __init__(self):
        pass
        
    def preprocess_name(self, name):
        """
        Preprocesses the name by converting to lowercase, removing punctuation,
        and extra whitespace.
        """
        if not name:
            return ""
            
        # Convert to lowercase
        name = name.lower()
        
        # Remove punctuation
        name = re.sub(r'[^\w\s]', '', name)
        
        # Remove extra whitespace
        name = re.sub(r'\s+', ' ', name).strip()
        
        return name
    
    def exact_match(self, name1, name2):
        """
        Checks if the names match exactly after preprocessing.
        Returns 1.0 for exact match, 0.0 otherwise.
        """
        name1 = self.preprocess_name(name1)
        name2 = self.preprocess_name(name2)
        
        return 1.0 if name1 == name2 else 0.0
    
    def sequence_match(self, name1, name2):
        """
        Uses Python's SequenceMatcher to compute a similarity ratio.
        Returns a score between 0.0 and 1.0.
        """
        name1 = self.preprocess_name(name1)
        name2 = self.preprocess_name(name2)
        
        return SequenceMatcher(None, name1, name2).ratio()
    
    def token_sort_ratio(self, name1, name2):
        """
        A simple implementation of token sort ratio without fuzzywuzzy.
        Sorts the tokens before comparison.
        Returns a score between 0.0 and 1.0.
        """
        name1 = self.preprocess_name(name1)
        name2 = self.preprocess_name(name2)
        
        # Sort tokens
        sorted_name1 = ' '.join(sorted(name1.split()))
        sorted_name2 = ' '.join(sorted(name2.split()))
        
        return SequenceMatcher(None, sorted_name1, sorted_name2).ratio()
    
    def token_set_ratio(self, name1, name2):
        """
        A simple implementation of token set ratio without fuzzywuzzy.
        Good for partial string matches.
        Returns a score between 0.0 and 1.0.
        """
        name1 = self.preprocess_name(name1)
        name2 = self.preprocess_name(name2)
        
        # Convert to sets to handle duplicates and order
        set1 = set(name1.split())
        set2 = set(name2.split())
        
        # Find intersections and differences
        intersection = set1.intersection(set2)
        diff1 = set1.difference(set2)
        diff2 = set2.difference(set1)
        
        # Calculate score based on intersection vs total
        if not (set1 or set2):
            return 0.0
            
        return len(intersection) / (len(intersection) + max(len(diff1), len(diff2)))
    
    def jaro_similarity(self, name1, name2):
        """
        A simple implementation of Jaro similarity without jellyfish.
        Returns a score between 0.0 and 1.0.
        """
        name1 = self.preprocess_name(name1)
        name2 = self.preprocess_name(name2)
        
        if not name1 or not name2:
            return 0.0 if name1 or name2 else 1.0
            
        # Implementation of Jaro similarity
        len1, len2 = len(name1), len(name2)
        
        # If both strings are empty, return 1.0
        if len1 == 0 and len2 == 0:
            return 1.0
            
        # Maximum distance between matching characters
        match_distance = max(len1, len2) // 2 - 1
        match_distance = max(0, match_distance)
        
        # Find matching characters within match_distance
        matches1 = [False] * len1
        matches2 = [False] * len2
        
        matches = 0
        for i in range(len1):
            start = max(0, i - match_distance)
            end = min(i + match_distance + 1, len2)
            
            for j in range(start, end):
                if not matches2[j] and name1[i] == name2[j]:
                    matches1[i] = True
                    matches2[j] = True
                    matches += 1
                    break
        
        # If no matches, return 0.0
        if matches == 0:
            return 0.0
            
        # Count transpositions
        transpositions = 0
        k = 0
        
        for i in range(len1):
            if matches1[i]:
                while not matches2[k]:
                    k += 1
                if name1[i] != name2[k]:
                    transpositions += 1
                k += 1
        
        # Calculate Jaro similarity
        return (matches / len1 + matches / len2 + (matches - transpositions / 2) / matches) / 3.0
    
    def levenshtein_distance(self, name1, name2):
        """
        Calculates the Levenshtein (edit) distance between two names.
        This is converted to a similarity score between 0.0 and 1.0.
        """
        name1 = self.preprocess_name(name1)
        name2 = self.preprocess_name(name2)
        
        if not name1 or not name2:
            return 0.0 if name1 or name2 else 1.0
            
        # Create a matrix
        rows = len(name1) + 1
        cols = len(name2) + 1
        distance = [[0 for _ in range(cols)] for _ in range(rows)]
        
        # Initialize the matrix
        for i in range(rows):
            distance[i][0] = i
        for j in range(cols):
            distance[0][j] = j
            
        # Fill the matrix
        for i in range(1, rows):
            for j in range(1, cols):
                if name1[i-1] == name2[j-1]:
                    distance[i][j] = distance[i-1][j-1]
                else:
                    distance[i][j] = min(
                        distance[i-1][j] + 1,     # deletion
                        distance[i][j-1] + 1,     # insertion
                        distance[i-1][j-1] + 1    # substitution
                    )
        
        # Convert distance to similarity score
        max_len = max(len(name1), len(name2))
        if max_len == 0:
            return 1.0
        return 1.0 - (distance[rows-1][cols-1] / max_len)
    
    def initials_match(self, name1, name2):
        """
        Checks if the initials of each word in the names match.
        Returns a score between 0.0 and 1.0.
        """
        name1 = self.preprocess_name(name1)
        name2 = self.preprocess_name(name2)
        
        words1 = name1.split()
        words2 = name2.split()
        
        # Get initials
        initials1 = ''.join([word[0] for word in words1 if word])
        initials2 = ''.join([word[0] for word in words2 if word])
        
        if not initials1 or not initials2:
            return 0.0
            
        # Compare initials using sequence matcher
        return SequenceMatcher(None, initials1, initials2).ratio()
    
    def match(self, name1, name2, method='weighted', weights=None):
        """
        Matches two names using the specified method or a weighted combination of methods.
        
        Parameters:
        name1 (str): First name to compare
        name2 (str): Second name to compare
        method (str): The matching method to use
        weights (dict): For 'weighted' method, a dictionary of method names and their weights
        
        Returns:
        float: A similarity score between 0.0 and 1.0
        """
        if not name1 or not name2:
            return 0.0
            
        # Default weights for weighted method
        default_weights = {
            'exact': 0.1,
            'sequence': 0.2,
            'token_sort': 0.2,
            'token_set': 0.2,
            'jaro': 0.2,
            'levenshtein': 0.05,
            'initials': 0.05
        }
        
        if method == 'exact':
            return self.exact_match(name1, name2)
        elif method == 'sequence':
            return self.sequence_match(name1, name2)
        elif method == 'token_sort':
            return self.token_sort_ratio(name1, name2)
        elif method == 'token_set':
            return self.token_set_ratio(name1, name2)
        elif method == 'jaro':
            return self.jaro_similarity(name1, name2)
        elif method == 'levenshtein':
            return self.levenshtein_distance(name1, name2)
        elif method == 'initials':
            return self.initials_match(name1, name2)
        elif method == 'weighted':
            # Use provided weights or defaults
            actual_weights = weights or default_weights
            
            # Normalize weights to sum to 1.0
            weight_sum = sum(actual_weights.values())
            if weight_sum <= 0:
                return 0.0
                
            normalized_weights = {k: v / weight_sum for k, v in actual_weights.items()}
            
            # Calculate weighted score
            score = 0.0
            if 'exact' in normalized_weights:
                score += normalized_weights['exact'] * self.exact_match(name1, name2)
            if 'sequence' in normalized_weights:
                score += normalized_weights['sequence'] * self.sequence_match(name1, name2)
            if 'token_sort' in normalized_weights:
                score += normalized_weights['token_sort'] * self.token_sort_ratio(name1, name2)
            if 'token_set' in normalized_weights:
                score += normalized_weights['token_set'] * self.token_set_ratio(name1, name2)
            if 'jaro' in normalized_weights:
                score += normalized_weights['jaro'] * self.jaro_similarity(name1, name2)
            if 'levenshtein' in normalized_weights:
                score += normalized_weights['levenshtein'] * self.levenshtein_distance(name1, name2)
            if 'initials' in normalized_weights:
                score += normalized_weights['initials'] * self.initials_match(name1, name2)
                
            return score
        else:
            frappe.throw(_("Unknown matching method: {0}").format(method))


# Create a singleton instance
matcher = NameMatcher()

@frappe.whitelist()
def match_names(name1, name2):
    """
    Whitelisted function to match names and return a similarity score.
    Uses an optimized combination of methods for best results.
    
    Parameters:
    name1 (str): First name to compare
    name2 (str): Second name to compare
    
    Returns:
    dict: Result dictionary with match score and details
    """
    try:
        # Use the optimized weighted method with predefined weights
        optimized_weights = {
            'token_set': 0.35,  # Best for handling word order and partial matches
            'jaro': 0.35,       # Best for name comparisons
            'sequence': 0.15,   # Good for overall string similarity
            'levenshtein': 0.15 # Good for handling typos and character differences
        }
        
        score = matcher.match(name1, name2, 'weighted', optimized_weights)
        
        return {
            'name1': name1,
            'name2': name2,
            'score': score * 100
        }
    except Exception as e:
        frappe.log_error(f"Name matching error: {str(e)}", "Name Matcher API")
        frappe.throw(_("Error in name matching: {0}").format(str(e)))


# Method selection API removed as we're using a fixed optimized method


@frappe.whitelist()
def batch_match_names(names_list, threshold=0.7):
    """
    Match multiple name pairs and return results filtered by threshold.
    Uses the same optimized algorithm as match_names.
    
    Parameters:
    names_list (str): JSON string of name pairs to compare [{"name1": "...", "name2": "..."}]
    threshold (float): Minimum score to include in results
    
    Returns:
    list: List of match results with scores above threshold
    """
    try:
        import json
        
        # Parse input
        if isinstance(names_list, str):
            names_list = json.loads(names_list)
        
        threshold = flt(threshold)
        
        # Use the same optimized weights as in match_names
        optimized_weights = {
            'token_set': 0.35,
            'jaro': 0.35,
            'sequence': 0.15,
            'levenshtein': 0.15
        }
        
        results = []
        for pair in names_list:
            if not isinstance(pair, dict) or 'name1' not in pair or 'name2' not in pair:
                continue
                
            name1 = pair.get('name1', '')
            name2 = pair.get('name2', '')
            
            score = matcher.match(name1, name2, 'weighted', optimized_weights)
            
            if score >= threshold:
                results.append({
                    'name1': name1,
                    'name2': name2,
                    'score': score
                })
                
        return results
    except Exception as e:
        frappe.log_error(f"Batch name matching error: {str(e)}", "Name Matcher API")
        frappe.throw(_("Error in batch name matching: {0}").format(str(e)))